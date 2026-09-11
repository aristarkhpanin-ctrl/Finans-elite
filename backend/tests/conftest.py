"""Общие фикстуры тестов API/персистентности: единый тестовый движок БД."""
import os

# По умолчанию rate-limit выключен в тестах: стор in-memory общий на весь прогон,
# а TestClient ходит с одного IP — иначе лимит /auth сорвётся на массе тестов.
# Отдельный тест (test_rate_limit) включает его точечно через monkeypatch.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

# Celery в тестах — eager (задачи выполняются синхронно в процессе, без брокера/воркера);
# результат хранится в in-memory бэкенде, доступном через AsyncResult.
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "1")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# Единая in-memory БД для тестов (общая на соединения через StaticPool).
_engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
_TestingSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def _override_get_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture
def client():
    """TestClient со свежей схемой БД на каждый тест (lifespan не запускаем)."""
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    return TestClient(app)


@pytest.fixture
def db_session(client):
    """Сессия к тестовой БД (схема уже создана фикстурой ``client``) — для crud-тестов."""
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def register(client):
    """Фабрика: зарегистрировать пользователя (создаёт организацию) → заголовки Bearer."""
    def _register(email: str = "owner@e.ru", org: str = "Орг") -> dict:
        token = client.post("/api/v1/auth/register", json={
            "email": email, "password": "secret123", "full_name": "Владелец",
            "organization_name": org,
        }).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return _register


@pytest.fixture
def auth_headers(register):
    """Заголовки авторизации владельца новой организации."""
    return register()
