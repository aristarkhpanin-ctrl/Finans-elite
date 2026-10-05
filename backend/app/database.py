"""Подключение к БД (SQLAlchemy 2.0).

По умолчанию — SQLite (для разработки/тестов); в продакшене указывается PostgreSQL через
переменную окружения ``DATABASE_URL`` (ARCHITECTURE-SaaS.md §14). JSON-поля на PostgreSQL
становятся ``JSONB``.

Для 6.1 схема создаётся через ``create_all`` (dev/test); Alembic-миграции — следующий
под-шаг, когда схема стабилизируется.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

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
#: Где сеанс работы с базой помнит своего арендатора (``Session.info``).
_TENANT_KEY = "rls_tenant"


@event.listens_for(engine, "checkout")
def _reset_tenant_on_checkout(dbapi_conn, _record, _proxy):
    """Сбрасывать арендатора соединения при выдаче из пула (защита от «залипшего» GUC).

    Арендатор теперь живёт в транзакции (:func:`_tenant_on_begin`) и с ней же кончается;
    сброс оставлен на случай, если кто-то выставит его на всё соединение мимо двери.
    """
    if engine.dialect.name != "postgresql":
        return
    cur = dbapi_conn.cursor()
    try:
        cur.execute("SELECT set_config(%s, '', false)", (_TENANT_GUC,))
    finally:
        cur.close()


def _apply_tenant(connection, org_id: str) -> None:
    """Арендатор — на **текущую транзакцию** (``set_config(…, true)`` = ``SET LOCAL``)."""
    connection.execute(text("SELECT set_config(:name, :val, true)"),
                       {"name": _TENANT_GUC, "val": org_id})


@event.listens_for(Session, "after_begin")
def _tenant_on_begin(session: Session, _transaction, connection) -> None:
    """Каждая транзакция сеанса начинается с его арендатора (L11).

    Раньше арендатор ставился на **соединение** — один раз, при входе запроса. Но сеанс
    после каждого ``commit`` возвращает соединение в пул, следующая операция берёт его
    заново, а пул при выдаче сбрасывает арендатора: всё, что запрос делал после первой
    записи, шло **без организации** — и под ролью без прав суперпользователя RLS
    отказывал (журнал не писался, чтение возвращало пустоту). Регистрация не проходила
    вовсе. Суперпользователь, которым приложение подключалось в `docker-compose.yml`,
    обходит RLS всегда, поэтому этого не видел ни один прогон.
    """
    if connection.dialect.name != "postgresql":
        return
    _apply_tenant(connection, session.info.get(_TENANT_KEY, ""))


def set_tenant(db: Session, org_id: str) -> None:
    """Выставить арендатора сеанса для RLS (PostgreSQL). На SQLite — запоминается, но
    ни на что не влияет: RLS там нет.

    Арендатор принадлежит **сеансу** (запросу), а не соединению: он переживает ``commit``
    и заново ставится в начале каждой транзакции (:func:`_tenant_on_begin`).
    """
    db.info[_TENANT_KEY] = org_id
    if db.in_transaction() and db.get_bind().dialect.name == "postgresql":
        _apply_tenant(db.connection(), org_id)


def current_tenant(db: Session) -> str:
    """Арендатор сеанса (пустая строка — никто)."""
    return db.info.get(_TENANT_KEY, "")


@contextmanager
def as_tenant(db: Session, org_id: str) -> Iterator[None]:
    """Войти в организацию как арендатор и выйти из неё, вернув прежнего.

    Дверь одна на всех, кто ходит по организациям в обход маршрута: служебный контур
    (B1), сводка платформы (B3) и свои данные человека (C3). **Обхода RLS у платформы
    нет** — входят через ту же дверь, что и участники организации, по одной.

    Оставленный от предыдущей организации арендатор — открытая дверь в чужие данные,
    которую никто не заметит: следующий запрос той же сессии прочитал бы не то, что
    просил. Выход обязателен и потому оформлен контекстом, а не парой вызовов.

    Возвращается **прежний** арендатор, а не пустота: дверь зовут и изнутри запроса, у
    которого арендатор уже выставлен (``deps.current_org_id``), и «выход в никуда»
    оставил бы остаток такого запроса без единой видимой строки.
    """
    previous = current_tenant(db)
    set_tenant(db, org_id)
    try:
        yield
    finally:
        set_tenant(db, previous)


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
