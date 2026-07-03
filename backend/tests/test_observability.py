"""Тесты наблюдаемости: request-id и обработчик расхождения инварианта."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability import setup_observability
from calc_core.engine.errors import InvariantError


def test_response_has_request_id(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID")  # идентификатор присвоен и возвращён


def test_incoming_request_id_is_echoed(client):
    r = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert r.headers.get("X-Request-ID") == "trace-123"


def test_invariant_error_returns_clean_500_with_request_id():
    # Изолированное приложение: маршрут, имитирующий баг ядра (InvariantError).
    app = FastAPI()
    setup_observability(app)

    @app.get("/boom")
    def boom():
        raise InvariantError("Баланс не сходится в периоде 3: B20=10 != B34=12")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/boom", headers={"X-Request-ID": "rid-9"})
    assert r.status_code == 500
    body = r.json()
    assert "инвариант" in body["detail"].lower()
    assert body["request_id"] == "rid-9"
    assert r.headers.get("X-Request-ID") == "rid-9"
