"""Подключение к БД (SQLAlchemy 2.0).

По умолчанию — SQLite (для разработки/тестов); в продакшене указывается PostgreSQL через
переменную окружения ``DATABASE_URL`` (ARCHITECTURE-SaaS.md §14). JSON-поля на PostgreSQL
становятся ``JSONB``.

Для 6.1 схема создаётся через ``create_all`` (dev/test); Alembic-миграции — следующий
под-шаг, когда схема стабилизируется.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./backend_dev.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


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
    """Создать таблицы (dev/test). В продакшене — Alembic."""
    from . import db_models  # noqa: F401 — регистрация моделей в метаданных
    Base.metadata.create_all(bind=engine)
