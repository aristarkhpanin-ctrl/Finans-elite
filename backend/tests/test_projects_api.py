"""Тесты персистентности проектов (6.1)."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# Изолированная in-memory БД для тестов (общая на соединения через StaticPool).
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
client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    yield


def _sample_model() -> dict:
    return client.get("/api/v1/sample").json()


def test_create_and_get_project():
    r = client.post("/api/v1/projects", json={"name": "Мой проект", "model": _sample_model()})
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "Мой проект"
    pid = created["id"]

    got = client.get(f"/api/v1/projects/{pid}")
    assert got.status_code == 200
    assert got.json()["model"]["header"]["duration_months"] == 12


def test_list_projects():
    client.post("/api/v1/projects", json={"name": "A", "model": _sample_model()})
    client.post("/api/v1/projects", json={"name": "B", "model": _sample_model()})
    r = client.get("/api/v1/projects")
    assert r.status_code == 200
    names = {p["name"] for p in r.json()}
    assert names == {"A", "B"}


def test_get_missing_404():
    assert client.get("/api/v1/projects/nope").status_code == 404


def test_update_project():
    pid = client.post("/api/v1/projects", json={"name": "Старое", "model": _sample_model()}).json()["id"]
    r = client.put(f"/api/v1/projects/{pid}", json={"name": "Новое"})
    assert r.status_code == 200
    assert r.json()["name"] == "Новое"


def test_delete_project():
    pid = client.post("/api/v1/projects", json={"name": "Удалить", "model": _sample_model()}).json()["id"]
    assert client.delete(f"/api/v1/projects/{pid}").status_code == 204
    assert client.get(f"/api/v1/projects/{pid}").status_code == 404


def test_calculate_stored_project():
    pid = client.post("/api/v1/projects", json={"name": "Расчёт", "model": _sample_model()}).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/calculate")
    assert r.status_code == 200
    data = r.json()
    assert data["n"] == 12
    b20 = next(l for l in data["balance"]["lines"] if l["code"] == "B20")["values"]
    b34 = next(l for l in data["balance"]["lines"] if l["code"] == "B34")["values"]
    for a, b in zip(b20, b34):
        assert abs(Decimal(a) - Decimal(b)) <= Decimal("0.01")


def test_create_invalid_model_422():
    bad = {"name": "Плохой", "model": {"header": {"duration_months": 0}}}
    assert client.post("/api/v1/projects", json=bad).status_code == 422
