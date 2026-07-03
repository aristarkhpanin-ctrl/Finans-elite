"""Подключение к БД (SQLAlchemy 2.0).

По умолчанию — SQLite (для разработки/тестов); в продакшене указывается PostgreSQL через
переменную окружения ``DATABASE_URL`` (ARCHITECTURE-SaaS.md §14). JSON-поля на PostgreSQL
становятся ``JSONB``.

Для 6.1 схема создаётся через ``create_all`` (dev/test); Alembic-миграции — следующий
под-шаг, когда схема стабилизируется.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./backend_dev.db")

_is_sqlite = DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
# Для сетевых БД (Postgres) — проверка живости соединения перед выдачей из пула и
# пересоздание раз в 30 мин: защита от «server closed the connection unexpectedly»
# (файрволы/таймауты БД рвут простаивающие соединения).
_pool_kwargs = {} if _is_sqlite else {"pool_pre_ping": True, "pool_recycle": 1800}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True, **_pool_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

#: Имя GUC-переменной арендатора для RLS (см. миграцию d5e8f1a2c3b4).
_TENANT_GUC = "app.current_org_id"


@event.listens_for(engine, "checkout")
def _reset_tenant_on_checkout(dbapi_conn, _record, _proxy):
    """Сбрасывать арендатора при выдаче соединения из пула (защита от «залипшего» GUC).

    Только PostgreSQL: незаданный/пустой GUC → RLS не покажет ни одной строки, пока
    запрос явно не выставит арендатора через :func:`set_tenant`.
    """
    if engine.dialect.name != "postgresql":
        return
    cur = dbapi_conn.cursor()
    try:
        cur.execute("SELECT set_config(%s, '', false)", (_TENANT_GUC,))
    finally:
        cur.close()


def set_tenant(db: Session, org_id: str) -> None:
    """Выставить арендатора для RLS на текущее соединение (PostgreSQL). На SQLite — no-op."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config(:name, :val, false)"),
                   {"name": _TENANT_GUC, "val": org_id})


class Base(DeclarativeBase):
    """Базовый класс ORM-моделей."""


def get_db():
    """FastAPI-зависимость: сессия БД на запрос."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Создать таблицы (dev/test). Идемпотентно (checkfirst).

    В продакшене источник истины по схеме — Alembic (``alembic upgrade head``);
    ``create_all`` при существующих таблицах ничего не делает.
    """
    from . import db_models  # noqa: F401 — регистрация моделей в метаданных
    Base.metadata.create_all(bind=engine)
