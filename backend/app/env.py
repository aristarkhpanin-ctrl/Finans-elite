"""Чтение настроек окружения: пустое значение — то же, что незаданное (пакет K, K6).

`docker-compose.yml` передаёт контейнерам каждую настройку как `${X:-}`, и незаданная у
владельца переменная приходит **пустой строкой**, а не отсутствием. `os.getenv(X, умолчание)`
на пустой строке умолчание не берёт: `int("")` ронял импорт (`JWT_REMEMBER_TTL_SECONDS`),
`SMTP_PORT` и `SMTP_TIMEOUT` — отправку письма, а пустой `MAIL_FROM` давал письмо без
отправителя. Одна дверь вместо разбора на каждом месте: забытое место снова уронило бы
запуск на чистой установке.
"""
from __future__ import annotations

import os


def env(name: str, default: str = "") -> str:
    """Значение переменной без пробелов по краям; пустое или незаданное — ``default``."""
    return os.getenv(name, "").strip() or default


def env_int(name: str, default: int) -> int:
    return int(env(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(env(name, str(default)))
