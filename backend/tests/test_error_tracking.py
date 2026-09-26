"""Трекер ошибок (пакет G, G7).

Проверяются обещания:

* без ``SENTRY_DSN`` трекер выключен, и ничего не отправляется — ни ошибок сервера, ни
  ошибок интерфейса; экран об этом знает из ``/auth/capabilities``;
* необработанная ошибка доходит до трекера **вычищенной**: без тела запроса, куки,
  строки запроса, заголовков авторизации, сведений о пользователе и локальных
  переменных, а почта, токены и ключи API в тексте скрыты (152-ФЗ);
* нарушение балансового инварианта отправляется **явно** — его обработчик отдаёт чистый
  500, и «необработанным» оно для трекера не является;
* ошибка интерфейса идёт тем же трекером и той же вычисткой, с пределами размера и
  частоты; неверный DSN называется и не роняет процесс.
"""
from __future__ import annotations

import json
import logging

import pytest
import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from app import error_tracking, ratelimit
from app.observability import setup_observability
from calc_core.engine.errors import InvariantError

DSN = "https://public@errors.example/1"


class Captured(Transport):
    """Транспорт в память: что трекер отправил бы."""

    def __init__(self):
        super().__init__()
        self.events: list[dict] = []

    def capture_envelope(self, envelope):
        event = envelope.get_event()
        if event is not None:
            self.events.append(event)


@pytest.fixture
def tracker(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", DSN)
    transport = Captured()
    assert error_tracking.init_error_tracking(component="api", transport=transport).enabled
    yield transport
    # Порядок важен: ``sentry_sdk.init()`` без адреса **сам читает SENTRY_DSN** из
    # окружения — вызванный до удаления переменной, он включал настоящий клиент, и
    # события следующих тестов уходили бы наружу. Пустая строка — явное «никуда».
    monkeypatch.delenv("SENTRY_DSN")
    sentry_sdk.init(dsn="")
    error_tracking.init_error_tracking(component="api")


def _app() -> TestClient:
    app = FastAPI()
    setup_observability(app)

    @app.post("/boom")
    def boom(payload: dict) -> dict:
        # Значение собирается во время выполнения: трекер прикладывает строки исходного
        # кода вокруг места ошибки, и литерал в исходнике проверял бы не то. Строки кода —
        # шаблоны платформы, а не данные клиента; значения переменных — данные.
        secret = "ИНН " + "".join(["7707", "083893"])  # noqa: F841 — не должна уйти
        raise RuntimeError("пользователь ivan@example.com не найден, token=abc123")

    @app.get("/invariant")
    def invariant() -> dict:
        raise InvariantError("B20 ≠ B34 на периоде 3")

    return TestClient(app, raise_server_exceptions=False)


def _dump(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False, default=str)


# --- Выключен без DSN ---

def test_without_a_dsn_the_tracker_is_off_and_says_so(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    state = error_tracking.init_error_tracking(component="api")
    assert state.enabled is False and "SENTRY_DSN" in state.reason
    assert error_tracking.capture_client_error(message="x", stack="", path="/", release="") \
        is False


def test_the_interface_is_told_whether_to_send(client, monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    error_tracking.init_error_tracking(component="api")
    assert client.get("/api/v1/auth/capabilities").json()["error_tracking"] is False


def test_a_bad_dsn_is_named_and_does_not_crash(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "это не адрес")
    state = error_tracking.init_error_tracking(component="api")
    assert state.enabled is False and "не принят" in state.reason
    monkeypatch.delenv("SENTRY_DSN")
    error_tracking.init_error_tracking(component="api")


# --- Ошибка сервера доходит вычищенной ---

def test_an_unhandled_error_reaches_the_tracker_scrubbed(tracker):
    client = _app()
    r = client.post("/boom?token=secret-link", json={"inn": "7707083893", "email": "a@b.ru"},
                    headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig",
                             "Cookie": "session=1", "X-Api-Key": "fe_0123abcd_secretsecret",
                             "User-Agent": "test-agent"})
    assert r.status_code == 500
    event = tracker.events[-1]
    text = _dump(event)
    assert "RuntimeError" in text and "[почта скрыта]" in text
    for leaked in ("ivan@example.com", "abc123", "secret-link", "eyJhbGci", "fe_0123abcd",
                   "7707083893", "a@b.ru", "session=1"):
        assert leaked not in text, leaked
    headers = {k.lower() for k in event["request"].get("headers", {})}
    assert headers <= error_tracking.SAFE_HEADERS and "user-agent" in headers
    assert "user" not in event and "data" not in event["request"]


def test_an_invariant_violation_reaches_the_tracker_exactly_once(tracker):
    """Обработчик отдаёт чистый 500, и ошибка «обработана» — но трекер получает и такие
    (ответ 5xx). Ровно одно событие: ноль значил бы, что самая важная ошибка методики
    молчит, два — что её отправляют дважды."""
    r = _app().get("/invariant")
    assert r.status_code == 500 and "инвариант" in r.json()["detail"]
    assert sum("InvariantError" in _dump(e) for e in tracker.events) == 1


def test_log_breadcrumbs_are_redacted_too(tracker):
    logging.getLogger("finans").warning("письмо не отправлено на petr@example.com")
    _app().post("/boom", json={})
    text = _dump(tracker.events[-1])
    assert "petr@example.com" not in text


# --- Ошибка интерфейса ---

def test_an_interface_error_goes_the_same_way(client, tracker):
    r = client.post("/api/v1/client-errors", json={
        "message": "TypeError: у ivan@example.com нет доступа",
        "stack": "at render (Tab.tsx:12)", "path": "/projects/p1?token=abc",
        "release": "2026.09"})
    assert r.status_code == 204
    event = tracker.events[-1]
    text = _dump(event)
    assert "ivan@example.com" not in text and "token=abc" not in text
    assert event["tags"]["component"] == "frontend" and event["tags"]["path"] == "/projects/p1"
    assert client.get("/api/v1/auth/capabilities").json()["error_tracking"] is True


def test_an_interface_error_with_the_tracker_off_is_accepted_and_dropped(client,
                                                                         monkeypatch):
    """Сломанный интерфейс не получает второй ошибки из-за того, что установка решила
    ошибок не собирать."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    error_tracking.init_error_tracking(component="api")
    assert client.post("/api/v1/client-errors", json={"message": "x"}).status_code == 204


def test_interface_errors_are_bounded_in_size_and_rate(client, monkeypatch):
    assert client.post("/api/v1/client-errors",
                       json={"message": "x" * 501}).status_code == 422
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    ratelimit._store.clear()
    try:
        codes = [client.post("/api/v1/client-errors", json={"message": "x"}).status_code
                 for _ in range(21)]
    finally:
        ratelimit._store.clear()
    assert codes[:20] == [204] * 20 and codes[20] == 429


# --- Вычистка: перечень разрешённого, а не запрещённого ---

def test_headers_are_an_allowlist_not_a_blocklist():
    event = {"request": {"url": "https://f.example/x?token=1#frag",
                         "headers": {"Content-Type": "application/json",
                                     "X-Some-New-Secret": "s3cr3t",
                                     "X-Forwarded-For": "10.0.0.7"}},
             "exception": {"values": [{"stacktrace": {"frames": [{"vars": {"a": 1}}]}}]}}
    out = error_tracking.scrub_event(event)
    assert out["request"]["headers"] == {"Content-Type": "application/json"}
    assert out["request"]["url"] == "https://f.example/x"
    assert "vars" not in out["exception"]["values"][0]["stacktrace"]["frames"][0]
