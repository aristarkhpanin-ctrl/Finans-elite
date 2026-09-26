"""Письма о деньгах (пакет G, G4).

До них платформа не писала о деньгах ни разу: предупреждение о льготном сроке жило
только баннером внутри продукта, и клиент, не заходивший эти две недели, узнавал о
проблеме, когда изменение данных уже закрылось. Проверяются обещания:

* три письма — за 7 дней до конца периода, в день окончания, при закрытии записи; каждое
  называет срок **числом** и выход (оплатить; оплата по счёту);
* повтор не уходит — факт отправки записан в журнале организации, по нему и сверка;
* получают те, кто вправе платить (``billing.manage``), и только действующие: ни
  приостановленный участник, ни заблокированная учётная запись;
* выключенная почта — **не пытались**, а не «отправили»: в журнал клиента ничего не
  пишется, и когда почту включат, письмо уйдёт;
* неудача отправки названа и **не гасит** повтор на следующий день;
* письма **дверные**: о доступе к своей организации, поэтому уходят и на
  неподтверждённый адрес.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import crud, mail, scheduler
from app.billing_period import GRACE_DAYS, reminder_stage
from app.database import as_tenant
from app.db_models import AuditLogEntry, Membership, User

NOW = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def post(monkeypatch):
    monkeypatch.setenv("MAIL_BACKEND", "memory")
    monkeypatch.setenv("PUBLIC_URL", "https://finans.example")
    mail.clear_outbox()
    yield mail.outbox
    mail.clear_outbox()


def _org(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _paid(db, org_id: str, *, ends_in: timedelta) -> None:
    crud.set_plan(db, org_id, "team", product="business", period_end=NOW + ends_in, paid=True)


def _reminders(db, org_id: str, action: str = "billing.reminder") -> list[AuditLogEntry]:
    with as_tenant(db, org_id):
        return list(db.query(AuditLogEntry).filter(
            AuditLogEntry.organization_id == org_id, AuditLogEntry.action == action).all())


def _to(outbox) -> list[str]:
    return [address for address, _ in outbox()]


# --- Этап письма: чистая функция над датой ---

@pytest.mark.parametrize("ends_in, expected", [
    (timedelta(days=8), None),                         # рано
    (timedelta(days=7), "ending"),                     # неделя до конца
    (timedelta(hours=5), "ending"),                    # последние часы — всё ещё «скоро»
    (timedelta(hours=-5), "ended"),                    # только что кончился
    (timedelta(days=-GRACE_DAYS), "ended"),            # последний день льготы
    (timedelta(days=-GRACE_DAYS - 1), "overdue"),      # льгота кончилась
])
def test_the_stage_follows_the_period(ends_in, expected):
    assert reminder_stage("active", NOW + ends_in, NOW) == expected


def test_no_period_no_letters():
    # «Не истекает» (бесплатный, пробный, «по запросу») — не «истёк давно».
    assert reminder_stage("active", None, NOW) is None


def test_a_cancelled_subscription_gets_no_reminders():
    # ``canceled`` — акт человека, автоматически его не ставит никто: о нём уже знают.
    assert reminder_stage("canceled", NOW + timedelta(days=3), NOW) is None


# --- Отправка ---

def test_a_week_before_the_owner_gets_a_letter_with_the_date_and_the_way_out(
        client, register, db_session, post):
    org_id = _org(client, register(email="owner@e.ru", org="ООО «Клиент»"))
    _paid(db_session, org_id, ends_in=timedelta(days=6, hours=2))

    scheduler.send_billing_reminders(db_session, NOW)

    assert _to(post) == ["owner@e.ru"]
    letter = post()[0][1]
    assert "ООО «Клиент»" in letter.text and "через 7 дн." in letter.text
    assert "https://finans.example/organization?tab=billing" in letter.text
    assert "по счёту" in letter.text                 # второй выход назван
    assert "просмотр, расчёт и выгрузка" in letter.text   # что останется, если не платить


def test_the_same_letter_does_not_go_twice(client, register, db_session, post):
    org_id = _org(client, register())
    _paid(db_session, org_id, ends_in=timedelta(days=5))
    scheduler.send_billing_reminders(db_session, NOW)
    scheduler.send_billing_reminders(db_session, NOW + timedelta(hours=12))
    assert len(post()) == 1
    assert len(_reminders(db_session, org_id)) == 1


def test_each_stage_is_its_own_letter(client, register, db_session, post):
    org_id = _org(client, register())
    _paid(db_session, org_id, ends_in=timedelta(days=5))
    scheduler.send_billing_reminders(db_session, NOW)                               # скоро
    scheduler.send_billing_reminders(db_session, NOW + timedelta(days=6))           # кончился
    scheduler.send_billing_reminders(db_session, NOW + timedelta(days=5 + GRACE_DAYS + 2))
    subjects = [letter.subject for _, letter in post()]
    assert len(subjects) == 3
    assert "заканчивается" in subjects[0] and "закончился" in subjects[1]
    assert "закрыто" in subjects[2]


def test_the_restriction_letter_says_what_still_works(client, register, db_session, post):
    org_id = _org(client, register())
    _paid(db_session, org_id, ends_in=-timedelta(days=GRACE_DAYS + 2))
    scheduler.send_billing_reminders(db_session, NOW)
    text = post()[0][1].text
    assert "закрыто до оплаты" in text and "выгрузка работают" in text


# --- Кому ---

def test_only_those_who_may_pay_receive(client, register, db_session, post):
    owner = register(email="owner@e.ru", org="Личная")
    org_id = client.post("/api/v1/organizations", json={"name": "Команда"},
                         headers=owner).json()["id"]
    owner_h = {**owner, "X-Organization-Id": org_id}
    register(email="analyst@e.ru", org="Личная аналитика")
    client.post(f"/api/v1/organizations/{org_id}/members",
                json={"email": "analyst@e.ru", "role": "analyst"}, headers=owner_h)
    _paid(db_session, org_id, ends_in=timedelta(days=3))

    scheduler.send_billing_reminders(db_session, NOW)
    assert "analyst@e.ru" not in _to(post)
    assert "owner@e.ru" in _to(post)


def test_a_suspended_member_and_a_blocked_account_receive_nothing(
        client, register, db_session, post):
    org_id = _org(client, register(email="owner@e.ru"))
    _paid(db_session, org_id, ends_in=timedelta(days=3))
    user = crud.get_user_by_email(db_session, "owner@e.ru")

    membership = db_session.query(Membership).filter_by(user_id=user.id).first()
    membership.blocked_at = NOW
    db_session.commit()
    scheduler.send_billing_reminders(db_session, NOW)
    assert post() == []

    membership.blocked_at = None
    db_session.query(User).filter_by(id=user.id).update({"blocked_at": NOW})
    db_session.commit()
    scheduler.send_billing_reminders(db_session, NOW)
    assert post() == []


def test_a_door_letter_goes_to_an_unverified_address(client, register, db_session, post):
    """Письмо о доступе к своей организации — не рассказ о чужой активности: запереть
    его за подтверждением значило бы узнать о закрытии записи уже после."""
    org_id = _org(client, register(email="owner@e.ru"))
    assert crud.get_user_by_email(db_session, "owner@e.ru").email_verified_at is None
    _paid(db_session, org_id, ends_in=timedelta(days=3))
    scheduler.send_billing_reminders(db_session, NOW)
    assert _to(post) == ["owner@e.ru"]


# --- Почта выключена и почта не ответила ---

def test_mail_off_means_not_attempted_and_the_letter_waits(
        client, register, db_session, monkeypatch):
    """«Не пытались» ≠ «отправили»: журнал клиента молчит, и включённая позже почта
    отправит то же письмо, а не решит, что оно уже ушло."""
    monkeypatch.setenv("MAIL_BACKEND", "off")
    org_id = _org(client, register())
    _paid(db_session, org_id, ends_in=timedelta(days=3))

    run = scheduler.send_billing_reminders(db_session, NOW)
    assert run.mail_off == 1 and run.sent == 0
    assert _reminders(db_session, org_id) == []
    assert "почта выключена" in crud.list_staff_log(db_session, limit=1)[0].details

    monkeypatch.setenv("MAIL_BACKEND", "memory")
    mail.clear_outbox()
    scheduler.send_billing_reminders(db_session, NOW)
    assert len(mail.outbox()) == 1
    mail.clear_outbox()


def test_a_failed_send_is_named_and_retried(client, register, db_session, post, monkeypatch):
    org_id = _org(client, register())
    _paid(db_session, org_id, ends_in=timedelta(days=3))
    monkeypatch.setattr(scheduler.mail, "send",
                        lambda to, letter: mail.Sent(ok=False, error="сервер не ответил"))

    run = scheduler.send_billing_reminders(db_session, NOW)
    assert run.failed == 1
    failed = _reminders(db_session, org_id, "billing.reminder_failed")
    assert len(failed) == 1 and "сервер не ответил" in failed[0].details
    assert _reminders(db_session, org_id) == []          # повтор не погашен

    monkeypatch.undo()
    monkeypatch.setenv("MAIL_BACKEND", "memory")
    scheduler.send_billing_reminders(db_session, NOW + timedelta(days=1))
    assert len(_reminders(db_session, org_id)) == 1


def test_without_a_public_address_the_letter_names_the_section(client, register, db_session,
                                                              post, monkeypatch):
    """Без ``PUBLIC_URL`` ссылка вела бы в никуда — письмо называет раздел словами."""
    monkeypatch.setenv("PUBLIC_URL", "")
    org_id = _org(client, register())
    _paid(db_session, org_id, ends_in=timedelta(days=3))
    scheduler.send_billing_reminders(db_session, NOW)
    text = post()[0][1].text
    assert "http" not in text and "«Тариф и оплата»" in text


def test_every_run_leaves_a_trace(db_session):
    scheduler.send_billing_reminders(db_session, NOW)
    assert scheduler.last_runs(db_session)["reminders"] is not None
