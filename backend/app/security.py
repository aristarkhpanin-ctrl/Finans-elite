"""Безопасность: хэш паролей (Argon2) и JWT-токены доступа.

Секрет и срок жизни токена — из окружения (``JWT_SECRET``, ``JWT_TTL_SECONDS``).
В продакшене ``JWT_SECRET`` обязателен (значение по умолчанию — только для разработки).
"""
from __future__ import annotations

import os
import time

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_ph = PasswordHasher()

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
JWT_TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", str(24 * 3600)))

# Заглушки, недопустимые в продакшене (код и .env.example).
_INSECURE_SECRETS = {"", "dev-secret-change-me", "change-me-in-production"}
_MIN_SECRET_LEN = 16


def _require_secure_secret(app_env: str, secret: str | None) -> None:
    """Fail-fast: в production JWT_SECRET обязан быть задан, не-заглушкой и достаточной длины.

    Иначе токены подписывались бы предсказуемым ключом — их мог бы подделать любой.
    Вне production (по умолчанию) — не мешаем разработке.
    """
    if app_env.strip().lower() != "production":
        return
    if not secret or secret in _INSECURE_SECRETS or len(secret) < _MIN_SECRET_LEN:
        raise RuntimeError(
            "JWT_SECRET обязателен в production (APP_ENV=production): задайте случайный "
            f"секрет не короче {_MIN_SECRET_LEN} символов и не равный заглушке."
        )


_require_secure_secret(os.getenv("APP_ENV", "development"), JWT_SECRET)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(hashed: str | None, password: str) -> bool:
    if not hashed:
        return False
    try:
        return _ph.verify(hashed, password)
    except Argon2Error:
        return False


#: Срок жизни приглашения. Неделя: приглашённый должен успеть зайти, но вечная
#: ссылка на заведение пароля — это вечная дыра, если письмо утекло.
INVITE_TTL_SECONDS = int(os.getenv("INVITE_TTL_SECONDS", str(7 * 24 * 3600)))


def _token(user_id: str, typ: str, ttl: int) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + ttl, "typ": typ},
                      JWT_SECRET, algorithm=JWT_ALG)


def create_access_token(user_id: str) -> str:
    return _token(user_id, "access", JWT_TTL_SECONDS)


def create_invite_token(user_id: str) -> str:
    """Токен приглашения: им заводят **пароль**, а не входят в систему."""
    return _token(user_id, "invite", INVITE_TTL_SECONDS)


def decode_token(token: str, expect: str = "access") -> str | None:
    """Вернуть user_id из валидного токена нужного назначения либо ``None``.

    Назначение проверяется обязательно. Без этого токен приглашения работал бы как
    токен входа: приглашённый попадал бы внутрь **до** того, как задал пароль, а
    сама ссылка-приглашение становилась бы вечным пропуском в чужую организацию.

    Токены без ``typ`` — выпущенные до разделения — считаются токенами доступа:
    иначе разделение выкинуло бы из системы всех, кто в ней сейчас сидит.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None
    if payload.get("typ", "access") != expect:
        return None
    return payload.get("sub")
