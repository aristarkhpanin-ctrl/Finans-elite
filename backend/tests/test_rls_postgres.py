"""RLS-тесты изоляции арендаторов на PostgreSQL (Фаза D).

Требуют реального Postgres (переменная ``TEST_PG_URL``) — на SQLite RLS нет. В CI
поднимается сервисный Postgres; локально можно указать свой инстанс.

Важно: RLS **не действует на суперпользователя** — поэтому и тест, и прод обязаны
работать под НЕ-суперпользовательской ролью. Здесь это моделируется ``SET ROLE``.
"""
from __future__ import annotations

import os
import shutil
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


# --- Приложение под настоящим RLS (пакет L, L11) ---
#
# Политики выше проверялись сами по себе. Ниже — то, как с ними живёт приложение: под
# ролью без прав суперпользователя (как в docker-compose.yml с L11) выяснилось, что
# арендатор терялся после первого commit запроса, а журнал без арендатора у запроса не
# писался вовсе — и регистрация не проходила. Суперпользователь, которым приложение
# подключалось до L11, обходит RLS всегда, поэтому этого не видел ни один прогон.


def _app_session(engine_url: str):
    """Сеанс приложения под ролью app_tenant: каждое новое соединение — от её имени."""
    from sqlalchemy import event
    from sqlalchemy.orm import sessionmaker

    eng = create_engine(engine_url, future=True, poolclass=NullPool)

    @event.listens_for(eng, "connect")
    def _as_app(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("SET ROLE app_tenant")
        cur.close()

    return sessionmaker(bind=eng)(), eng


def test_the_tenant_survives_commits(clean):
    """После commit сеанс берёт новое соединение — арендатор обязан прийти вместе с ним."""
    from app.database import set_tenant

    db, eng = _app_session(PG_URL)
    try:
        set_tenant(db, "orgA")
        db.execute(_INSERT_PROJECT, {"id": "p1", "org": "orgA"})
        db.commit()
        db.execute(_INSERT_PROJECT, {"id": "p2", "org": "orgA"})   # вторая запись запроса
        db.commit()
        assert sorted(db.execute(text("SELECT id FROM projects")).scalars()) == ["p1", "p2"]
    finally:
        db.close()
        eng.dispose()


def test_the_journal_is_written_without_a_request_tenant(clean):
    """Регистрация заводит организацию и тут же пишет о ней — арендатора у запроса ещё
    нет. Запись идёт в дверях своей организации и видна ей одной."""
    from app import crud
    from app.database import set_tenant

    db, eng = _app_session(PG_URL)
    try:
        crud.log_action(db, "orgA", None, "org.create", entity_type="organization",
                        entity_id="orgA", entity_name="orgA")
        set_tenant(db, "orgA")
        assert db.execute(text("SELECT count(*) FROM audit_log")).scalar_one() == 1
        set_tenant(db, "orgB")
        assert db.execute(text("SELECT count(*) FROM audit_log")).scalar_one() == 0
    finally:
        db.close()
        eng.dispose()


@pytest.mark.skipif(shutil.which("psql") is None, reason="нужен клиент psql")
def test_the_app_role_script_hands_the_database_to_a_plain_role(pg_engine):
    """`ops/db/app-role.sql`: роль без прав суперпользователя, владелец базы и таблиц —
    и повторный прогон ничего не ломает (скрипт идёт при каждом старте установки)."""
    from sqlalchemy.engine import make_url

    scratch = "finans_role_check"
    url = make_url(PG_URL)
    with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {scratch}"))
        c.execute(text(f"CREATE DATABASE {scratch}"))
    target = url.set(database=scratch)
    try:
        subprocess.run(["alembic", "upgrade", "head"], cwd=_BACKEND, check=True,
                       env={**os.environ,
                            "DATABASE_URL": target.render_as_string(hide_password=False)})
        env = {**os.environ, "PGHOST": url.host or "localhost", "PGPORT": str(url.port or 5432),
               "PGUSER": url.username or "", "PGPASSWORD": url.password or "",
               "PGDATABASE": scratch}
        script = _BACKEND.parent / "ops" / "db" / "app-role.sql"
        for _ in range(2):                                   # идемпотентность
            subprocess.run(["psql", "-q", "-v", "app_password=проверка", "-f", str(script)],
                           check=True, env=env)
        eng = create_engine(target, future=True, poolclass=NullPool)
        with eng.connect() as c:
            assert c.execute(text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'finans_app'"
            )).one() == (False, False)
            foreign = c.execute(text(
                "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' "
                "AND tableowner <> 'finans_app'")).scalar_one()
            assert foreign == 0
            assert c.execute(text(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = :d"),
                {"d": scratch}).scalar_one() == "finans_app"
        eng.dispose()
    finally:
        with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {scratch}"))


def test_readiness_names_a_role_that_bypasses_rls(clean):
    """Суперпользователь — проблема «Готовности»; роль без прав — в порядке, с числом
    политик. Проверяется роль, которой подключено приложение, а не настройка."""
    from sqlalchemy.orm import sessionmaker

    from app import readiness

    su = sessionmaker(bind=create_engine(PG_URL, future=True, poolclass=NullPool))()
    try:
        item = readiness._rls(su)
        assert item.status == "problem" and "суперпользователь" in item.state
    finally:
        su.close()
    db, eng = _app_session(PG_URL)
    try:
        item = readiness._rls(db)
        assert item.status == "ok" and "app_tenant" in item.state, item
    finally:
        db.close()
        eng.dispose()
