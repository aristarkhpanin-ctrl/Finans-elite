"""Общие фикстуры тестов API/персистентности: единый тестовый движок БД."""
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
def org_headers(client):
    """Создать организацию и вернуть заголовок арендатора."""
    org = client.post("/api/v1/organizations", json={"name": "Орг"}).json()
    return {"X-Organization-Id": org["id"]}
