"""Планировщик (пакет G, G3).

Проверяется то, ради чего его заводили: сверка неоплаты идёт **сама**, оставляет след в
журнале клиента, идемпотентна — и **каждый** запуск оставляет след в служебном журнале,
даже когда делать было нечего. По этому следу экран готовности отвечает «работает ли
планировщик»; молчание журнала означает «не запускался», а не «всё хорошо».

И ещё два обещания, которые держат перечни: в расписании нет задачи, которую Celery не
знает (опечатка в имени молча выключила бы её навсегда), и у скрипта эксплуатации нет
своей копии сверки — он зовёт ту же функцию, что и планировщик.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

from app import crud, scheduler
from app.billing_period import GRACE_DAYS, PERIOD_DAYS
from app.celery_app import celery_app
from app.database import as_tenant
from app.db_models import AuditLogEntry


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _lapsed(client, db_session, headers, *, days_overdue: int) -> str:
    """Организация с оплаченным тарифом, период которого кончился ``days_overdue`` назад."""
    org_id = _org_id(client, headers)
    end = datetime.now(timezone.utc) - timedelta(days=days_overdue)
    crud.set_plan(db_session, org_id, "team", product="business", period_end=end, paid=True)
    return org_id


def _journal(db_session, org_id: str) -> list[AuditLogEntry]:
    with as_tenant(db_session, org_id):
        return list(db_session.query(AuditLogEntry)
                    .filter(AuditLogEntry.organization_id == org_id,
                            AuditLogEntry.action == "billing.overdue").all())


# --- Сверка неоплаты ---

def test_an_overdue_subscription_goes_past_due_and_the_client_journal_says_so(
        client, register, db_session):
    org_id = _lapsed(client, db_session, register(), days_overdue=GRACE_DAYS + 3)

    changed = scheduler.expire_overdue(db_session, datetime.now(timezone.utc))

    assert [s.organization_id for s, _ in changed] == [org_id]
    assert crud.get_subscription(db_session, org_id, "business").status == "past_due"
    entries = _journal(db_session, org_id)
    assert len(entries) == 1 and "истекли" in entries[0].details


def test_grace_is_not_overdue(client, register, db_session):
    """Льготный срок настоящий: пока он идёт, подписку не трогают."""
    org_id = _lapsed(client, db_session, register(), days_overdue=GRACE_DAYS - 1)
    assert scheduler.expire_overdue(db_session, datetime.now(timezone.utc)) == []
    assert crud.get_subscription(db_session, org_id, "business").status == "active"


def test_the_sweep_is_idempotent(client, register, db_session):
    org_id = _lapsed(client, db_session, register(), days_overdue=GRACE_DAYS + 3)
    now = datetime.now(timezone.utc)
    scheduler.expire_overdue(db_session, now)
    assert scheduler.expire_overdue(db_session, now) == []
    assert len(_journal(db_session, org_id)) == 1        # второй запуск клиенту не пишет


def test_dry_run_changes_nothing_and_leaves_no_trace(client, register, db_session):
    org_id = _lapsed(client, db_session, register(), days_overdue=GRACE_DAYS + 3)
    changed = scheduler.expire_overdue(db_session, datetime.now(timezone.utc), dry_run=True)
    assert len(changed) == 1
    assert crud.get_subscription(db_session, org_id, "business").status == "active"
    assert _journal(db_session, org_id) == []
    assert scheduler.last_runs(db_session)["expire"] is None


# --- След запуска ---

def test_every_run_leaves_a_trace_even_when_there_was_nothing_to_do(db_session):
    """«Проверили — просроченных нет» — тоже ответ. Без следа он неотличим от «не
    запускались», а это ровно то, что экран готовности должен различать."""
    runs = scheduler.last_runs(db_session)
    assert set(runs) == set(scheduler.TASKS)                        # каждая задача названа
    assert all(moment is None for moment in runs.values())          # ни разу — не ноль
    scheduler.expire_overdue(db_session, datetime.now(timezone.utc))
    assert scheduler.last_runs(db_session)["expire"] is not None
    entry = crud.list_staff_log(db_session, limit=1)[0]
    assert entry.action == "scheduler.expire" and "нет" in entry.details
    assert entry.actor_email == ""                                  # это платформа, не человек


# --- Перечни ---

def test_the_schedule_names_only_tasks_celery_knows():
    """Опечатка в имени задачи молча выключила бы её навсегда: beat ставил бы в очередь
    задачу, которой воркер не знает."""
    import app.tasks  # noqa: F401  — регистрирует задачи
    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert scheduled, "расписание пусто"
    assert scheduled <= set(celery_app.tasks), scheduled - set(celery_app.tasks)


def test_every_scheduler_task_is_on_the_schedule():
    """И обратно: задача планировщика, которой нет в расписании, не запустится никогда."""
    import app.tasks  # noqa: F401
    ours = {name for name in celery_app.tasks if name.startswith("scheduler.")}
    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert ours == scheduled


def test_the_script_has_no_copy_of_the_sweep():
    """Скрипт эксплуатации и задача планировщика зовут одну функцию: две копии одной
    сверки однажды разошлись бы."""
    import scripts.expire_subscriptions as script
    source = inspect.getsource(script)
    # Смотрим на вызовы, а не на слова: докстринг скрипта объясняет, что доступ решает
    # ``effective_status``, — упоминание не копия.
    assert "expire_overdue(" in source
    assert "effective_status(" not in source and "log_action(" not in source


def test_period_constants_are_what_the_tests_assume():
    # Сторож допущений этого файла: льгота короче периода, и «+3 дня» действительно за ней.
    assert 0 < GRACE_DAYS < PERIOD_DAYS


# --- Обёртки: задача планировщика и скрипт зовут одну функцию, след подписан ---

def test_the_task_runs_the_sweep_and_signs_the_trace(client, register, db_session,
                                                     monkeypatch):
    from sqlalchemy.orm import sessionmaker

    import app.tasks as tasks
    monkeypatch.setattr(tasks, "SessionLocal", sessionmaker(bind=db_session.get_bind()))
    org_id = _lapsed(client, db_session, register(), days_overdue=GRACE_DAYS + 3)

    assert tasks.expire_subscriptions_task() == 1
    db_session.expire_all()
    assert crud.get_subscription(db_session, org_id, "business").status == "past_due"
    assert crud.list_staff_log(db_session, limit=1)[0].details.startswith("планировщик")


def test_a_manual_script_run_does_not_pass_for_the_scheduler(client, register, db_session,
                                                             monkeypatch, capsys):
    """Ручной запуск — тоже сверка, но экран готовности спрашивает о планировщике: след
    подписан «скрипт эксплуатации», и за работающий планировщик его не примут."""
    from sqlalchemy.orm import sessionmaker

    import scripts.expire_subscriptions as script
    monkeypatch.setattr(script, "SessionLocal", sessionmaker(bind=db_session.get_bind()))
    _lapsed(client, db_session, register(), days_overdue=GRACE_DAYS + 3)

    assert script.main([]) == 0
    assert "→ past_due" in capsys.readouterr().out
    db_session.expire_all()
    assert crud.list_staff_log(db_session, limit=1)[0].details.startswith("скрипт эксплуатации")
