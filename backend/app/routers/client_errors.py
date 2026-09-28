"""Ошибки интерфейса — в тот же трекер, что и ошибки сервера (пакет G, G7).

Через свой маршрут, а не прямо из браузера: адрес трекера не попадает в сборку
интерфейса (его можно было бы вынуть и засыпать трекер чем угодно), вычистка — одна,
серверная, и пределы размера и частоты — у нас, а не на доверии к браузеру.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from .. import error_tracking
from ..ratelimit import rate_limit

router = APIRouter(prefix="/api/v1", tags=["errors"])


class ClientErrorIn(BaseModel):
    """Ошибка интерфейса: что, где и в какой сборке. Без содержимого экрана и адреса
    страницы целиком — путь без строки запроса (в ней ходят токены ссылок)."""

    message: str = Field(max_length=error_tracking.CLIENT_MESSAGE_MAX)
    stack: str = Field(default="", max_length=error_tracking.CLIENT_STACK_MAX)
    path: str = Field(default="", max_length=300)
    release: str = Field(default="", max_length=40)


@router.post("/client-errors", status_code=204,
             dependencies=[Depends(rate_limit("client_errors", limit=20, window_seconds=60))])
def report_client_error(body: ClientErrorIn) -> Response:
    """Принять ошибку интерфейса. Вход не нужен: ломается и экран входа.

    Трекер выключен — ответ тот же (204), и ничего не происходит: сломанный интерфейс
    не должен получать вторую ошибку из-за того, что установка решила ошибок не
    собирать. Экран и так не шлёт их там, где трекера нет (``/auth/capabilities``).
    """
    error_tracking.capture_client_error(message=body.message, stack=body.stack,
                                        path=body.path, release=body.release)
    return Response(status_code=204)
