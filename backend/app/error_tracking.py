"""Трекер ошибок (пакет G, G7) — Sentry-совместимый (подходит и GlitchTip у себя).

До него ошибки жили только в логах процесса: чтобы узнать об упавшем расчёте, кто-то
должен был читать логи, а первым о поломке платформа узнавала от клиента.

Три правила важнее кода:

* **Без ``SENTRY_DSN`` трекер выключен и не отправляет ничего** — даже не импортирует
  пакет. Куда уходят ошибки установки — решение её владельца, а не умолчание продукта.
  Состояние (:func:`state`) названо словами для экрана готовности (G9).
* **До отправки вычищается всё, что может нести сведения о людях или числа клиентов**
  (152-ФЗ): тело запроса, куки, строка запроса (в ней ходят токены ссылок), заголовки
  кроме короткого перечня, сведения о пользователе, локальные переменные кадров, а в
  оставшемся тексте — почта, токены и ключи API. Отчёт об ошибке нужен, чтобы найти
  **место** поломки, а не чтобы узнать, у кого и на каких числах она случилась.
* **Нарушение балансового инварианта доходит до трекера**, хотя его перехватывает свой
  обработчик и отдаёт клиенту чистый 500: уходит **запись лога уровня ERROR** с
  трассировкой (интеграция логирования отправляет такие записи как события). Здесь
  стояло «отправляется явно, иначе не дошло бы ни разу» — снятие показало, что это
  неправда: явная отправка давала то же одно событие (повтор трекер отбрасывает), а
  держит всё запись лога. Явную отправку убрали, тест держит «ровно одно событие» и
  падает, если запись понизить. Следствие, которое надо помнить: **любой** ``log.error``
  приложения становится событием трекера — и проходит ту же вычистку.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

#: Переменная окружения с адресом трекера.
DSN_ENV = "SENTRY_DSN"

#: Заголовки, которые остаются в отчёте. Всё прочее (Authorization, Cookie, ключи API,
#: X-Forwarded-For с адресом человека) вычищается: перечень разрешённого, а не
#: запрещённого — новый заголовок с секретом не проскочит, потому что его забыли назвать.
SAFE_HEADERS = frozenset({"content-type", "content-length", "user-agent", "x-request-id"})

_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[почта скрыта]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"), "[токен скрыт]"),
    (re.compile(r"\bfe_[0-9a-f]{8}_[A-Za-z0-9_-]+"), "[ключ скрыт]"),
    (re.compile(r"(?i)\b(token|password|secret|key)=[^&\s\"']+"), r"\1=[скрыто]"),
]


@dataclass(frozen=True)
class TrackerState:
    """Включён ли трекер — и если нет, почему (словами, для экрана готовности)."""

    enabled: bool
    reason: str = ""


_OFF = TrackerState(False, "SENTRY_DSN не задан — ошибки никуда не отправляются, "
                           "их видно только в логах процесса")
_state: TrackerState = _OFF


def state() -> TrackerState:
    return _state


def redact(text: str) -> str:
    """Вычистить из строки почту, токены, ключи API и секреты в параметрах."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _redact_tree(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: _redact_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_tree(v) for v in value]
    return value


def scrub_event(event: dict, hint: dict | None = None) -> dict:
    """Вычистить событие перед отправкой. Зовётся трекером на каждом событии.

    Сначала — структурно (что не нужно для поиска места поломки, уходит целиком), затем
    — текст всего, что осталось: сообщение ошибки часто само несёт адрес («пользователь
    a@b.ru не найден»), и вычищать только заголовки значило бы пропустить его.
    """
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string", "env"):
            request.pop(key, None)
        if isinstance(request.get("url"), str):
            request["url"] = request["url"].split("?", 1)[0].split("#", 1)[0]
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items()
                                  if k.lower() in SAFE_HEADERS}
    event.pop("user", None)
    event.pop("extra", None)
    for exc in (event.get("exception") or {}).get("values") or []:
        for frame in (exc.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    for thread in (event.get("threads") or {}).get("values") or []:
        for frame in (thread.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    return _redact_tree(event)


def init_error_tracking(*, component: str, transport: Any = None) -> TrackerState:
    """Включить трекер, если задан ``SENTRY_DSN``. Ошибка настройки не роняет процесс.

    ``component`` — какой процесс сообщает (``api``, ``worker``): упавший ночной запуск
    и упавший запрос — разные разговоры. ``transport`` — только для тестов.
    """
    global _state
    dsn = os.getenv(DSN_ENV, "").strip()
    if not dsn:
        _state = _OFF
        return _state
    try:
        import sentry_sdk
    except ImportError:
        _state = TrackerState(False, "SENTRY_DSN задан, но пакет sentry-sdk не установлен "
                                     "— ошибки не отправляются")
        return _state
    from calc_core import ENGINE_VERSION

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("APP_ENV", "development"),
            release=f"finans@{ENGINE_VERSION}",
            server_name=component,
            send_default_pii=False,
            include_local_variables=False,
            max_request_body_size="never",
            traces_sample_rate=0.0,
            # Одна дверь: хлебные крошки (строки логов перед ошибкой) уходят только
            # внутри события, а событие целиком проходит вычистку.
            before_send=scrub_event,
            transport=transport,
        )
    except Exception as exc:  # noqa: BLE001 — неверный DSN не должен ронять приложение
        _state = TrackerState(False, f"SENTRY_DSN не принят: {exc}")
        return _state
    _state = TrackerState(True)
    return _state


#: Пределы отчёта из интерфейса: сообщение, стек и путь — не больше этого.
CLIENT_MESSAGE_MAX = 500
CLIENT_STACK_MAX = 4000


def capture_client_error(*, message: str, stack: str, path: str, release: str) -> bool:
    """Ошибка интерфейса — тем же трекером и той же вычисткой. ``False`` — выключен."""
    if not _state.enabled:
        return False
    import sentry_sdk

    sentry_sdk.capture_event({
        "level": "error",
        "logger": "frontend",
        "message": message[:CLIENT_MESSAGE_MAX],
        "tags": {"component": "frontend", "path": path.split("?", 1)[0][:200],
                 "frontend_release": release[:40]},
        "extra": {},
        "contexts": {"frontend": {"stack": stack[:CLIENT_STACK_MAX]}},
    })
    return True
