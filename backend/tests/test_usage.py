"""События пользования продуктом (NEXT-STEPS.md, E2).

Проверяются четыре обещания слоя: перечень закрыт и весь используется, чисел клиента в
событиях нет, участник обезличен, сбор выключается рубильником и ничего не роняет.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import usage
from app.db_models import UsageEvent

APP = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture
def collecting(monkeypatch):
    """Включить сбор на время теста: по умолчанию он выключен."""
    monkeypatch.setenv("USAGE_EVENTS", "1")
    monkeypatch.setenv("USAGE_SALT", "соль-теста")


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _events(db) -> list[UsageEvent]:
    return list(db.query(UsageEvent).order_by(UsageEvent.created_at).all())


# --- Рубильник ---

def test_nothing_is_collected_by_default(client, register, db_session):
    """Сбор данных о пользовании — решение владельца установки, а не умолчание:
    включённый молча, он превращает продукт в то, чего покупатель не заказывал."""
    headers = register()
    client.post("/api/v1/projects", json={"name": "П", "model":
                client.get("/api/v1/sample").json()}, headers=headers)
    assert _events(db_session) == []


def test_the_switch_turns_it_on(client, register, db_session, collecting):
    register()
    assert [e.event for e in _events(db_session)] == ["signup"]


# --- Перечень ---

def test_every_event_in_the_catalogue_is_actually_recorded():
    """Событие, которого никто не пишет, — обещание данных, которые не придут.

    Так из перечня уже выпало «открыл результаты»: отдельного маршрута у экрана
    результатов нет, он зовёт расчёт, и событие было бы вторым именем того же самого.
    """
    source = "\n".join(p.read_text() for p in APP.rglob("*.py"))
    written = set(re.findall(r'record\(\s*db,\s*event="([a-z_.]+)"', source))
    assert set(usage.EVENTS) == written, (
        "перечень и код разошлись: "
        f"не пишутся {sorted(set(usage.EVENTS) - written)}, "
        f"пишутся мимо перечня {sorted(written - set(usage.EVENTS))}")


def test_an_unknown_event_is_not_written(db_session, collecting):
    """«Почти правильный» код события хуже отсутствующего: его потом ищут в отчётах."""
    assert usage.record(db_session, event="project.opened", org_id="o1") is None
    assert _events(db_session) == []


# --- Что в событии есть и чего в нём нет ---

def test_no_number_from_the_clients_model_can_get_in(db_session, collecting):
    """Правило 6 пакета A→D («оператор не читает модели») действует и здесь."""
    usage.record(db_session, event="project.calculate", org_id="o1",
                 context={"npv": "123456", "revenue": "999", "product": "business"})
    (event,) = _events(db_session)
    assert event.context == {"product": "business"}


def test_context_values_are_too_short_for_a_report(db_session, collecting):
    usage.record(db_session, event="project.export", org_id="o1",
                 context={"source": "x" * 500})
    (event,) = _events(db_session)
    assert len(event.context["source"]) == 64


def test_the_participant_is_a_fingerprint_not_an_address(db_session, collecting):
    """«Тот же человек вернулся» — да; «кто именно» — нет."""
    usage.record(db_session, event="signup", org_id="o1", email="Ivan@Company.RU")
    (event,) = _events(db_session)
    assert "@" not in event.actor and event.actor != "ivan@company.ru"
    # Регистр адреса когорту не ломает: это один и тот же человек.
    assert event.actor == usage.fingerprint("ivan@company.ru")


def test_a_system_event_has_no_author(db_session, collecting):
    """Пустой отпечаток честнее выдуманного: событие без человека не притворяется чьим-то."""
    usage.record(db_session, event="project.open", org_id="o1")
    assert _events(db_session)[0].actor == ""


def test_the_fingerprint_depends_on_the_installation(db_session, monkeypatch):
    """Без соли отпечаток — это словарь почт, а не обезличивание."""
    monkeypatch.setenv("USAGE_SALT", "первая")
    first = usage.fingerprint("k@e.ru")
    monkeypatch.setenv("USAGE_SALT", "вторая")
    assert usage.fingerprint("k@e.ru") != first


# --- Слой не мешает работе ---

def test_a_broken_recording_does_not_break_the_users_work(db_session, collecting,
                                                          monkeypatch):
    """Аналитика стоит в стороне от работы: падение записи не должно ронять то, ради
    чего человек пришёл."""
    def boom(*a, **kw):
        raise RuntimeError("база сказала нет")

    monkeypatch.setattr(db_session, "commit", boom)
    assert usage.record(db_session, event="signup", org_id="o1") is None


def test_usage_is_not_the_journal(client, register, db_session, collecting):
    """Две таблицы на два разных вопроса: журнал отвечает клиенту «кто это сделал» и не
    пишет чтение, события отвечают платформе «как пользуются» и пишут именно чтение."""
    from app.db_models import AuditLogEntry

    headers = register()
    pid = client.post("/api/v1/projects", json={"name": "П", "model":
                      client.get("/api/v1/sample").json()},
                      headers=headers).json()["id"]
    client.get(f"/api/v1/projects/{pid}", headers=headers)      # чтение
    client.post(f"/api/v1/projects/{pid}/calculate", headers=headers)

    events = {e.event for e in _events(db_session)}
    actions = {e.action for e in db_session.query(AuditLogEntry).all()}
    # Чтение и расчёт есть в событиях и **отсутствуют** в журнале.
    assert {"project.open", "project.calculate"} <= events
    assert "project.open" not in actions and "project.calculate" not in actions
    # А «кто создал проект» есть в журнале — там это вопрос клиента.
    assert "project.create" in actions


def test_events_are_written_for_both_products(client, register, db_session, collecting):
    headers = register()
    client.post("/api/v1/audit/subjects",
                json={"name": "Дело", "model": {"name": "Дело", "periods": [],
                                                "lines": []}}, headers=headers)
    sid = client.get("/api/v1/audit/subjects", headers=headers).json()[0]["id"]
    client.post(f"/api/v1/audit/subjects/{sid}/analyze", headers=headers)

    events = {e.event for e in _events(db_session)}
    assert {"case.create", "case.analyze"} <= events


def test_the_organization_is_a_cut_not_an_owner(client, register, db_session,
                                                collecting):
    """Таблица не принадлежит арендатору: она про пользование платформой, и организация
    в ней — разрез. Поэтому RLS на ней нет, и читает её только служебный контур."""
    register()
    second = register(email="other@e.ru", org="Другая")
    _org_id(client, second)
    orgs = {e.organization_id for e in _events(db_session)}
    assert len(orgs) == 2
