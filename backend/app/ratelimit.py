"""Ограничение частоты запросов (защита `/auth` от перебора).

In-memory скользящее окно по ключу «bucket:client-ip» — без внешних зависимостей.
Достаточно для одного инстанса; при горизонтальном масштабировании ключи стоит
вынести в общий стор (Redis) — см. ROADMAP, Фаза D.

Включение — переменной окружения ``RATE_LIMIT_ENABLED`` (по умолчанию включено;
в тестах выключается в ``conftest``). За обратным прокси реальный IP берётся из
первого элемента ``X-Forwarded-For`` (nginx подставляет его, см. nginx.conf).
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


def _enabled() -> bool:
    return os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() not in ("0", "false", "no", "")


def _client_ip(request: Request) -> str:
    """IP клиента: первый хоп X-Forwarded-For (за доверенным прокси) либо peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class _SlidingWindow:
    """Потокобезопасное скользящее окно: не более ``limit`` событий за ``window`` сек."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        """Зарегистрировать попытку. Вернуть (разрешено, Retry-After сек)."""
        now = time.monotonic()
        cutoff = now - window
        with self._lock:
            dq = self._hits[key]
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= limit:
                retry_after = int(window - (now - dq[0])) + 1
                return False, retry_after
            dq.append(now)
            return True, 0

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


_store = _SlidingWindow()


def rate_limit(bucket: str, limit: int, window_seconds: float):
    """FastAPI-зависимость: не более ``limit`` запросов за окно с одного IP.

    Применяется через ``dependencies=[Depends(rate_limit(...))]`` на роутере —
    сигнатуру эндпоинта не меняет. Превышение → ``429`` с ``Retry-After``.
    """

    def dependency(request: Request) -> None:
        if not _enabled():
            return
        allowed, retry_after = _store.check(f"{bucket}:{_client_ip(request)}", limit, window_seconds)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много запросов. Повторите попытку позже.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
