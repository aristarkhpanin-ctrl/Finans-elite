"""Выгрузка событийной сводки (OPEN-DECISIONS §7).

Сырые события означали бы выгрузку поведения людей, пусть и обезличенных. Поэтому
выгружается **агрегат, в котором участника нет вовсе**: месяц, событие, организация,
число — и сколько разных людей за ним стоит.

Проверяется граница, а не формат: отпечатка в файле нет, удержание уходит уже
посчитанным, оговорки едут в самом файле, пустой файл объясняет свою пустоту, а читать
его может только сотрудник платформы.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import crud, usage
from app.db_models import StaffLogEntry, UsageEvent


@pytest.fixture
def collecting(monkeypatch):
    monkeypatch.setenv("USAGE_EVENTS", "1")
    monkeypatch.setenv("USAGE_SALT", "соль-теста")


def _staff(client, db_session, register, email="staff@e.ru") -> dict:
    headers = register(email=email, org="Наша платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, email), is_staff=True)
    return headers


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _csv(client, staff, **params) -> str:
    r = client.get("/api/v1/admin/usage.csv", params=params, headers=staff)
    assert r.status_code == 200
    return r.content.decode("utf-8-sig")


def _event(db, org_id, event, *, email="k@e.ru", when=None) -> UsageEvent:
    row = UsageEvent(organization_id=org_id, event=event,
                     actor=usage.fingerprint(email), context={},
                     created_at=when or datetime.now(timezone.utc))
    db.add(row)
    db.commit()
    return row


# --- Участника в файле нет ---

def test_the_file_carries_no_fingerprint_at_all(client, register, db_session, collecting):
    """Отпечаток нужен внутри — ответить «тот же человек вернулся». Вне платформы его
    рано или поздно соединят с чем-то ещё, и обезличенность кончится."""
    owner = register()
    org = _org_id(client, owner)
    staff = _staff(client, db_session, register)
    _event(db_session, org, "project.create", email="ivan@e.ru")

    text = _csv(client, staff)
    assert usage.fingerprint("ivan@e.ru") not in text
    assert "ivan@e.ru" not in text
    # И сказано, что его нет намеренно, а не потерялся.
    assert "ни почты, ни отпечатка" in text


def test_how_many_people_is_not_who_they_are(client, register, db_session, collecting):
    """«Десять событий от одного человека» и «десять от десяти» — разные факты, и без
    этого числа их не различить. Само число отпечатком не является."""
    owner = register()
    org = _org_id(client, owner)
    for email in ("a@e.ru", "b@e.ru", "a@e.ru"):
        _event(db_session, org, "project.calculate", email=email)

    row = next(r for r in usage.summarize(db_session).rows
               if r.event == "project.calculate")
    assert row.count == 3 and row.participants == 2


def test_a_system_event_without_a_person_counts_nobody(client, register, db_session,
                                                        collecting):
    """Пустой отпечаток — событие без человека, и приписывать ему участника нельзя."""
    owner = register()
    org = _org_id(client, owner)
    _event(db_session, org, "billing.paid", email="")

    row = next(r for r in usage.summarize(db_session).rows if r.event == "billing.paid")
    assert row.count == 1 and row.participants == 0


# --- Что в файле есть ---

def test_the_row_is_month_event_organization_number(client, register, db_session,
                                                     collecting):
    owner = register(org="ООО «Клиент»")
    org = _org_id(client, owner)
    staff = _staff(client, db_session, register)
    _event(db_session, org, "project.create")

    text = _csv(client, staff)
    month = f"{datetime.now(timezone.utc):%Y-%m}"
    assert "Месяц;Событие;Что это;Организация;Идентификатор;Событий;Участников" in text
    assert f"{month};project.create;{usage.EVENTS['project.create']};ООО «Клиент»" in text


def test_monthly_totals_keep_the_empty_months(client, register, db_session, collecting):
    """Пропущенный месяц в ряду читается как потерянные данные, а ноль в нём — это
    ответ (то же правило, что в сводке платформы)."""
    register()
    staff = _staff(client, db_session, register)
    summary = usage.summarize(db_session, months=6)
    # Шесть месяцев окна — все в ряду; прошлые нулевые, текущий несёт регистрацию.
    assert len(summary.monthly) == 6
    assert [v for _, v in summary.monthly[:-1]] == [0, 0, 0, 0, 0]
    assert summary.monthly[-1][1] > 0

    text = _csv(client, staff, months=6)
    assert "Месяц;Событий всего" in text
    assert f"{summary.monthly[0][0]};0" in text


def test_events_outside_the_window_do_not_leak_in(client, register, db_session,
                                                   collecting):
    owner = register()
    org = _org_id(client, owner)
    old = datetime.now(timezone.utc) - timedelta(days=400)
    _event(db_session, org, "project.create", when=old)
    _event(db_session, org, "project.calculate")

    summary = usage.summarize(db_session, months=3)
    events = [r.event for r in summary.rows]
    assert "project.calculate" in events
    # Старое событие того же вида в окно не попало (оно одно — создание проекта).
    assert "project.create" not in events
    # Но дата первого события считается **по всем** событиям: окно сужает выдачу, а не
    # историю, и «собираем с такого-то числа» обязано остаться правдой.
    assert summary.first_event_at is not None
    assert summary.first_event_at.date() == old.date()


def test_retention_goes_out_already_computed(client, register, db_session, collecting):
    """Пересчитывать долю снаружи означало бы, что снаружи есть, из чего."""
    owner = register()
    org = _org_id(client, owner)
    staff = _staff(client, db_session, register)
    now = datetime.now(timezone.utc)
    _event(db_session, org, "signup", when=now - timedelta(days=70))
    _event(db_session, org, "project.calculate", when=now)

    text = _csv(client, staff, months=6)
    assert "Когорта;Пришло организаций;Вернулось;Доля вернувшихся" in text
    assert ";1;1;1,00" in text


# --- Оговорки едут в файле ---

def test_the_caveats_travel_inside_the_file(client, register, db_session, collecting):
    """Таблица, доехавшая до чужой презентации без оговорок, утверждает больше, чем
    платформа измеряла."""
    owner = register()
    _event(db_session, _org_id(client, owner), "project.create")
    staff = _staff(client, db_session, register)

    text = _csv(client, staff)
    assert "Чего эти числа не значат" in text
    assert "Это не журнал действий" in text
    assert "Первое событие записано" in text
    assert "отсутствие строки — это ноль" in text


def test_an_empty_file_explains_itself_instead_of_refusing(client, register, db_session):
    """Сбор выключен по умолчанию, и «событий нет» без оговорки читается как «никто не
    пользовался». Отказ здесь был бы хуже: файл умеет объяснить себя сам."""
    register()
    staff = _staff(client, db_session, register)

    text = _csv(client, staff)
    assert "Событий не записано ни одного" in text
    assert "рубильником" in text
    assert "Сбор событий сейчас выключен" in text


def test_when_collection_is_on_the_file_says_so(client, register, db_session, collecting):
    register()
    staff = _staff(client, db_session, register)
    assert "Сбор событий сейчас включён" in _csv(client, staff)


# --- Кто это читает ---

def test_only_a_platform_operator_can_take_the_file(client, register, db_session):
    headers = register()
    assert client.get("/api/v1/admin/usage.csv", headers=headers).status_code == 403


def test_taking_the_file_is_written_to_the_staff_log(client, register, db_session,
                                                     collecting):
    """Вынос следов наружу — тоже событие, и о нём журнал иначе умолчал бы (правило A2)."""
    register()
    staff = _staff(client, db_session, register)
    _csv(client, staff)

    actions = [e.action for e in db_session.query(StaffLogEntry).all()]
    assert "staff.usage_export" in actions
