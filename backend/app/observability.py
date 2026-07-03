"""Наблюдаемость: структурные логи, request-id и сигнал о расхождении инварианта.

Каждый запрос получает идентификатор (заголовок ``X-Request-ID`` или сгенерированный),
который проставляется во все логи запроса и возвращается в ответе — сквозная трассировка.

Ключевое для точностного продукта: нарушение балансового инварианта (``InvariantError`` —
баг методики, B20≠B34) раньше уходило безымянной 500 без следов. Теперь оно логируется
на уровне ERROR с сообщением ядра (период и значения) и трассировкой, а клиенту отдаётся
чистый 500 с request-id для диагностики.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from calc_core.engine.errors import InvariantError

#: Идентификатор текущего запроса (для логов). Обновляется middleware на каждый запрос.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

log = logging.getLogger("finans")

# Санитизация входящего X-Request-ID: безопасный набор символов и длина.
_RID_DISALLOWED = re.compile(r"[^A-Za-z0-9._-]")


def _clean_request_id(raw: str | None) -> str:
    """Очистить входящий request-id (защита от log/header-инъекций: \\r\\n и пр.).

    Оставляем только [A-Za-z0-9._-], не длиннее 64; пусто → генерируем.
    """
    cleaned = _RID_DISALLOWED.sub("", raw or "")[:64]
    return cleaned or uuid.uuid4().hex[:12]


class _RequestIdFilter(logging.Filter):
    """Проставляет ``request_id`` из contextvar в каждую запись лога."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging() -> None:
    """Настроить логгер ``finans`` (уровень — из ``LOG_LEVEL``, по умолчанию INFO).

    Конфигурируется именно наш логгер, а не root — чтобы не мешать окружению (uvicorn,
    тестовому захвату логов).
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    )
    log.handlers[:] = [handler]
    log.setLevel(level)
    log.propagate = False


def setup_observability(app: FastAPI) -> None:
    """Подключить логирование, request-id middleware и обработчик InvariantError."""
    configure_logging()

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = _clean_request_id(request.headers.get("X-Request-ID"))
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000
            log.info("%s %s → %s (%.0f ms)", request.method, request.url.path,
                     response.status_code, duration_ms)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_var.reset(token)

    @app.exception_handler(InvariantError)
    async def on_invariant_error(request: Request, exc: InvariantError):
        # Баг методики: баланс не сошёлся. Громкий лог с контекстом ядра и трассировкой.
        log.error("Нарушение инварианта расчёта на %s: %s", request.url.path, exc, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Внутренняя ошибка расчёта (нарушен балансовый инвариант).",
                "request_id": request_id_var.get(),
            },
        )
