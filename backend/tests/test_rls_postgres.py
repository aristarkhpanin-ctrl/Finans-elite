"""RLS-тесты изоляции арендаторов на PostgreSQL (Фаза D).

Требуют реального Postgres (переменная ``TEST_PG_URL``) — на SQLite RLS нет. В CI
поднимается сервисный Postgres; локально можно указать свой инстанс.

Важно: RLS **не действует на суперпользователя** — поэтому и тест, и прод обязаны
работать под НЕ-суперпользовательской ролью. Здесь это моделируется ``SET ROLE``.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

PG_URL = os.getenv("TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="RLS: задайте TEST_PG_URL (Postgres)")

_BACKEND = Path(__file__).resolve().parents[1]

_INSERT_PROJECT = text(
    "INSERT INTO projects (id, organization_id, name, model, created_at, updated_at) "
    "VALUES (:id, :org, :id, '{}'::jsonb, now(), now())"
)


def _set_org(conn, org: str) -> None:
    conn.execute(text("SELECT set_config('app.current_org_id', :o, false)"), {"o": org})


_DROP_ROLE = text(
    "DO $$ BEGIN "
    "  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_tenant') THEN "
    "    EXECUTE 'DROP OWNED BY app_tenant'; EXECUTE 'DROP ROLE app_tenant'; "
    "  END IF; "
    "END $$;"
)


@pytest.fixture(scope="module")
def pg_engine():
    # Применяем реальные миграции (включая RLS-политику) и заводим НЕ-суперпользователя.
    subprocess.run(["alembic", "upgrade", "head"], cwd=_BACKEND, check=True,
                   env={**os.environ, "DATABASE_URL": PG_URL})
    # NullPool: каждое соединение свежее — SET ROLE / GUC не «залипают» между блоками.
    eng = create_engine(PG_URL, future=True, poolclass=NullPool)
    with eng.begin() as c:
        c.execute(_DROP_ROLE)  # идемпотентно (снимает гранты прошлого прогона)
        c.execute(text("CREATE ROLE app_tenant NOSUPERUSER"))
        c.execute(text("GRANT USAGE ON SCHEMA public TO app_tenant"))
        c.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_tenant"))
    yield eng
    with eng.begin() as c:
        c.execute(text("TRUNCATE projects, holdings, organizations CASCADE"))
        c.execute(_DROP_ROLE)
    eng.dispose()


@pytest.fixture
def clean(pg_engine):
    with pg_engine.begin() as c:
        c.execute(text("TRUNCATE projects, holdings, organizations CASCADE"))
        c.execute(text("INSERT INTO organizations (id, name, created_at) VALUES "
                       "('orgA','orgA',now()), ('orgB','orgB',now())"))
    return pg_engine


def test_select_isolated_between_tenants(clean):
    with clean.begin() as c:
        c.execute(text("SET ROLE app_tenant"))  # под RLS
        _set_org(c, "orgA")
        c.execute(_INSERT_PROJECT, {"id": "pa", "org": "orgA"})
        _set_org(c, "orgB")
        c.execute(_INSERT_PROJECT, {"id": "pb", "org": "orgB"})

    with clean.connect() as c:
        c.execute(text("SET ROLE app_tenant"))
        _set_org(c, "orgA")
        assert c.execute(text("SELECT id FROM projects")).scalars().all() == ["pa"]
        _set_org(c, "orgB")
        assert c.execute(text("SELECT id FROM projects")).scalars().all() == ["pb"]
        _set_org(c, "")  # арендатор не задан → ни одной строки (deny-by-default)
        assert c.execute(text("SELECT id FROM projects")).scalars().all() == []


def test_insert_for_foreign_tenant_blocked(clean):
    with clean.connect() as c:
        c.execute(text("SET ROLE app_tenant"))
        _set_org(c, "orgA")
        # organization_id чужого арендатора нарушает WITH CHECK политики.
        with pytest.raises(ProgrammingError):
            c.execute(_INSERT_PROJECT, {"id": "x", "org": "orgB"})


def test_superuser_note_role_matters(clean):
    # Демонстрация важности роли: суперпользователь обходит RLS (видит всё) —
    # поэтому приложение обязано подключаться НЕ-суперпользователем.
    with clean.begin() as c:
        c.execute(text("SET ROLE app_tenant"))
        _set_org(c, "orgA")
        c.execute(_INSERT_PROJECT, {"id": "pa", "org": "orgA"})
        c.execute(text("RESET ROLE"))  # снова суперпользователь
        _set_org(c, "orgB")            # арендатор B, но…
        # …суперпользователь всё равно видит проект A (RLS его не касается).
        assert c.execute(text("SELECT id FROM projects")).scalars().all() == ["pa"]
