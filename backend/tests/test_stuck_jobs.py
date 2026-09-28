"""Оповещение о зависших задачах анализа (пакет G, G8).

До него зависший Монте-Карло платформа узнавала от клиента по телефону: вкладка
«Эксплуатация» показывала задачу, но на неё надо было смотреть. Проверяются обещания:

* **порог — решение эксплуатации**: не задан — ничего не проверяется, и след запуска
  это называет; неверный или больше часа — назван и не применяется (состояние задачи
  Celery хранит час, и дальше «зависла» не отличить от «посчитана давно»);
* письмо — операторам, одно на задачу: повтор сверяется по служебному журналу;
* зависла — это «в очереди» или «считается» дольше порога; упавшая — не зависла;
* молчание брокера — не «зависла», а «неизвестно», и писем о нём нет;
* письмо информационное: на неподтверждённый адрес не уходит, поддержка и
  заблокированные его не получают; выключенная почта — «не пытались»;
* запускается часто, а след пишет не чаще раза в час, если нового нет, — и всегда,
  если есть.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import crud, mail, scheduler
from app.db_models import AnalysisJob, StaffLogEntry

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def post(monkeypatch):
    monkeypatch.setenv("MAIL_BACKEND", "memory")
    monkeypatch.setenv("STUCK_JOB_ALERT_MINUTES", "30")
    mail.clear_outbox()
    yield mail.outbox
    mail.clear_outbox()


def _operator(db, register, email="ops@platform.ru", role="operator", verified=True):
    register(email=email, org="Платформа")
    user = crud.get_user_by_email(db, email)
    crud.set_staff(db, user, is_staff=True, role=role)
    if verified:
        user.email_verified_at = NOW
        db.commit()
    return user


def _job(db, client, register, *, age_minutes: int, job_id: str = "job-1") -> AnalysisJob:
    headers = register(email=f"client-{job_id}@e.ru", org="ООО «Клиент»")
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    job = AnalysisJob(id=job_id, organization_id=org_id, project_id="p1", kind="monte_carlo",
                      created_at=NOW - timedelta(minutes=age_minutes))
    db.add(job)
    db.commit()
    return job


def _fetch(state: str):
    return lambda job_id: (state, None)


def _alerts(db) -> list[StaffLogEntry]:
    return list(db.query(StaffLogEntry).filter_by(action="jobs.stuck_alert").all())


# --- Порог ---

def test_without_a_threshold_nothing_is_checked_and_the_trace_says_so(db_session,
                                                                      monkeypatch):
    monkeypatch.delenv("STUCK_JOB_ALERT_MINUTES", raising=False)
    calls = []
    run = scheduler.check_stuck_jobs(db_session, NOW,
                                     fetch=lambda j: calls.append(j) or ("STARTED", None))
    assert run.threshold is None and calls == []
    assert "порог не задан" in crud.list_staff_log(db_session, limit=1)[0].details


@pytest.mark.parametrize("raw", ["полчаса", "90", "0"])
def test_a_bad_threshold_is_named_and_not_applied(db_session, monkeypatch, raw):
    monkeypatch.setenv("STUCK_JOB_ALERT_MINUTES", raw)
    minutes, problem = scheduler.stuck_threshold()
    assert minutes is None
    assert raw == "0" and problem is None or problem and "STUCK_JOB_ALERT_MINUTES" in problem


# --- Что считается зависшим ---

def test_a_job_running_past_the_threshold_alerts_the_operator_once(
        client, register, db_session, post):
    _operator(db_session, register)
    _job(db_session, client, register, age_minutes=40)
    run = scheduler.check_stuck_jobs(db_session, NOW, fetch=_fetch("STARTED"))
    assert run.stuck == 1 and run.alerted == 1
    to, letter = post()[0]
    assert to == "ops@platform.ru" and letter.informational
    assert "ООО «Клиент»" in letter.text and "40 мин" in letter.text and "30 мин" in letter.text
    assert "Эксплуатация" in letter.text

    scheduler.check_stuck_jobs(db_session, NOW + timedelta(minutes=10), fetch=_fetch("STARTED"))
    assert len(post()) == 1 and len(_alerts(db_session)) == 1          # одно на задачу


@pytest.mark.parametrize("state, age", [("PENDING", 20), ("SUCCESS", 45), ("FAILURE", 45)])
def test_young_finished_and_failed_jobs_are_not_stuck(client, register, db_session, post,
                                                      state, age):
    """Упавшая задача — не зависшая: она уже сказала своё, и её видно на вкладке."""
    _operator(db_session, register)
    _job(db_session, client, register, age_minutes=age)
    assert scheduler.check_stuck_jobs(db_session, NOW, fetch=_fetch(state)).stuck == 0
    assert post() == []


def test_a_silent_broker_is_unknown_not_stuck(client, register, db_session, post):
    _operator(db_session, register)
    _job(db_session, client, register, age_minutes=45)

    def silent(job_id):
        raise ConnectionError("redis недоступен")

    run = scheduler.check_stuck_jobs(db_session, NOW, fetch=silent)
    assert run.stuck == 0 and run.unknown == 1 and post() == []
    assert "не ответило" in crud.list_staff_log(db_session, limit=1)[0].details


# --- Кому ---

def test_support_blocked_and_unverified_staff_receive_nothing(client, register, db_session,
                                                              post):
    _operator(db_session, register, email="support@platform.ru", role="support")
    _operator(db_session, register, email="unverified@platform.ru", verified=False)
    blocked = _operator(db_session, register, email="blocked@platform.ru")
    blocked.blocked_at = NOW
    db_session.commit()
    _job(db_session, client, register, age_minutes=40)
    run = scheduler.check_stuck_jobs(db_session, NOW, fetch=_fetch("STARTED"))
    assert post() == [] and run.alerted == 0
    assert _alerts(db_session) == []                  # не ушло — повтор не погашен


def test_mail_off_is_not_attempted_and_waits(client, register, db_session, monkeypatch):
    monkeypatch.setenv("STUCK_JOB_ALERT_MINUTES", "30")
    monkeypatch.setenv("MAIL_BACKEND", "off")
    _operator(db_session, register)
    _job(db_session, client, register, age_minutes=40)
    run = scheduler.check_stuck_jobs(db_session, NOW, fetch=_fetch("STARTED"))
    assert run.stuck == 1 and run.alerted == 0 and _alerts(db_session) == []
    assert "почта выключена" in crud.list_staff_log(db_session, limit=1)[0].details


# --- След запуска ---

def test_quiet_runs_leave_a_trace_at_most_hourly_news_always(client, register, db_session,
                                                              post, monkeypatch):
    """Запуск частый (порог меньше часа, а состояние живёт час), и след каждого утопил
    бы служебный журнал. Молчание журнала всё равно значит «не запускался»: тихий
    запуск пишет след, если прошлому больше часа."""
    def traces() -> int:
        return db_session.query(StaffLogEntry).filter_by(
            action=scheduler.TASKS["stuck"]).count()

    scheduler.check_stuck_jobs(db_session, NOW, fetch=_fetch("SUCCESS"))
    scheduler.check_stuck_jobs(db_session, NOW + timedelta(minutes=10), fetch=_fetch("SUCCESS"))
    assert traces() == 1                                  # тихо и недавно — без следа
    _operator(db_session, register)
    # К проверке (NOW+20) задаче 45 минут: дольше порога, но в пределах часа хранения
    # состояния — старше её судьбу уже не узнать, и она честно выпала бы из окна.
    _job(db_session, client, register, age_minutes=25)
    scheduler.check_stuck_jobs(db_session, NOW + timedelta(minutes=20), fetch=_fetch("STARTED"))
    assert traces() == 2                                  # новость — след всегда
    # След записан настоящим временем, и давность меряется им же: «час спустя» — это
    # часы планировщика, а не время проверки задач.
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    monkeypatch.setattr(scheduler, "_wall_clock", lambda: later)
    scheduler.check_stuck_jobs(db_session, NOW + timedelta(minutes=90), fetch=_fetch("SUCCESS"))
    assert traces() == 3                                  # час прошёл — след снова
    assert scheduler.last_runs(db_session)["stuck"] is not None
