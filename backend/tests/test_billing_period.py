"""Срок оплаченного периода и неоплата (OPEN-DECISIONS §1).

До этого подписка **не кончалась**: все три места, менявшие её, ставили `active`, а
`current_period_end` не заполнял никто. Оплаченный один раз тариф действовал вечно, а
весь механизм B2 («режим чтения и выгрузки при неоплате») — написанный, оттестированный
и умеющий объяснить клиенту причину — не мог включиться ни по какому пути продукта.

Проверяется не арифметика дат, а обещания: срок ставит **платёж**, бесплатный тариф
**не истекает**, льготный срок **настоящий** (работа продолжается, клиент предупреждён),
и платформа **никогда не говорит «вы отменили подписку»** сама.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import crud
from app.access import restriction_for
from app.billing import activate_paid_plan
from app.billing_period import (
    GRACE_DAYS,
    PERIOD_DAYS,
    effective_status,
    grace_days_left,
    in_grace,
    paid_period_end,
)
from app.plans import PLANS

NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _expire(db, org_id: str, *, days_ago: int, product="business") -> None:
    """Сдвинуть конец оплаченного периода в прошлое на `days_ago` суток."""
    sub = crud.get_subscription(db, org_id, product)
    sub.current_period_end = datetime.now(timezone.utc) - timedelta(days=days_ago)
    db.commit()


# --- Срок ставит платёж, а не смена тарифа ---

def test_a_paid_plan_gets_a_period_and_a_free_one_does_not():
    """`None` — это «не истекает», а не «истёк давно». Читатель поля обязан различать:
    за бесплатный тариф не платили, и отнимать у него нечего."""
    assert paid_period_end(PLANS["team"], NOW) == NOW + timedelta(days=PERIOD_DAYS)
    assert paid_period_end(PLANS["free"], NOW) is None
    assert paid_period_end(PLANS["audit_trial"], NOW) is None
    # «По запросу» — тоже: его условия согласуют вне продукта, и тридцать дней с момента,
    # когда оператор его поставил, были бы выдуманным сроком.
    assert paid_period_end(PLANS["audit_corp"], NOW) is None


def test_a_client_cannot_assign_itself_a_paid_plan_at_all(client, register, db_session):
    """Здесь стояло правило «смена тарифа правом `billing.manage` — назначение, а не
    покупка: отсчёт не начинается». Правило было верным про отсчёт и **неверным про
    право**: `billing.manage` есть у владельца организации-клиента, и «административная»
    смена оказалась самовыдачей — платный тариф брался бесплатно и не истекал никогда.

    F1 закрыл дорогу целиком: клиент этим маршрутом идёт только вниз. Отсчёт по-прежнему
    начинает оплата, а назначение без оплаты (оператором, `months=None`) — по-прежнему
    нет; это проверяет `test_staff_subscription.py`.
    """
    headers = register()
    org = _org_id(client, headers)
    r = client.post(f"/api/v1/organizations/{org}/subscription",
                    json={"plan_code": "team"}, headers=headers)
    assert r.status_code == 403
    sub = crud.get_subscription(db_session, org, "business")
    assert sub is None or sub.plan_code == "free"


def test_paying_starts_the_clock(client, register, db_session):
    headers = register()
    org = _org_id(client, headers)
    activate_paid_plan(db_session, org, PLANS["team"])
    sub = crud.get_subscription(db_session, org, "business")
    assert sub.status == "active" and sub.current_period_end is not None


def test_moving_to_a_free_plan_clears_a_foreign_deadline(client, register, db_session):
    """Перейдя с платного на бесплатный, организация не должна тащить чужой срок —
    иначе бесплатный тариф однажды «истечёт»."""
    headers = register()
    org = _org_id(client, headers)
    activate_paid_plan(db_session, org, PLANS["team"])
    activate_paid_plan(db_session, org, PLANS["free"])
    assert crud.get_subscription(db_session, org, "business").current_period_end is None


# --- Что делает время ---

def test_a_period_that_has_not_ended_changes_nothing():
    future = NOW + timedelta(days=5)
    assert effective_status("active", future, NOW) == "active"
    assert in_grace(future, NOW) is False


def test_the_grace_period_is_real_work_not_a_countdown_to_nothing():
    """Пока идёт льготный срок, статус не меняется: ограничение в день окончания
    периода — не строгость, а ловушка."""
    for day in (1, GRACE_DAYS // 2, GRACE_DAYS):
        ended = NOW - timedelta(days=day)
        assert effective_status("active", ended, NOW) == "active", f"день {day}"
        assert in_grace(ended, NOW) is True
        assert grace_days_left(ended, NOW) == GRACE_DAYS - day


def test_after_the_grace_period_the_subscription_is_overdue_not_cancelled():
    """Платформа **никогда** не говорит «вы отменили подписку» сама: `canceled` — это
    акт, и приписывать его забывшему карту нельзя. Неуплата даёт `past_due` — буквально
    то, что произошло."""
    long_gone = NOW - timedelta(days=GRACE_DAYS + 1)
    assert effective_status("active", long_gone, NOW) == "past_due"
    assert effective_status("active", NOW - timedelta(days=400), NOW) == "past_due"


def test_a_plan_without_a_deadline_never_expires():
    assert effective_status("active", None, NOW) == "active"
    assert in_grace(None, NOW) is False


def test_time_does_not_heal_a_status_set_by_a_human():
    """Истёкшая дата не может сделать подписку действующей; отменённая — тем более."""
    assert effective_status("canceled", NOW + timedelta(days=30), NOW) == "canceled"
    assert effective_status("past_due", None, NOW) == "past_due"


def test_a_naive_deadline_is_read_as_utc():
    """SQLite отдаёт наивные datetime, PostgreSQL — с зоной. Сравнение тех и других
    роняет расчёт на одной базе и молча проходит на другой."""
    naive = (NOW - timedelta(days=GRACE_DAYS + 1)).replace(tzinfo=None)
    assert effective_status("active", naive, NOW) == "past_due"


# --- Что видит клиент ---

def test_during_grace_the_client_is_warned_but_not_stopped(client, register, db_session):
    """Предупреждение едет **тем же каналом**, что и отказ: второй канал однажды забыли
    бы показать, и клиент узнал бы о проблеме в день, когда уже ничего не может."""
    headers = register()
    org = _org_id(client, headers)
    activate_paid_plan(db_session, org, PLANS["team"])
    _expire(db_session, org, days_ago=3)

    restriction = restriction_for(db_session, org, "business")
    assert restriction is not None and restriction.kind == "grace"
    assert restriction.blocking is False
    assert f"{GRACE_DAYS - 3} " in restriction.remedy          # названо число, а не «скоро»

    # И запись при этом работает: льготный срок — не полу-ограничение.
    model = client.get("/api/v1/sample").json()
    created = client.post("/api/v1/projects", json={"name": "В льготный срок",
                                                    "model": model}, headers=headers)
    assert created.status_code == 201


def test_after_grace_the_read_only_mode_finally_switches_itself_on(client, register,
                                                                  db_session):
    """То, ради чего всё и делалось: механизм B2 не мог включиться ни по какому пути
    продукта — `past_due` в базе не появлялся никогда."""
    headers = register()
    org = _org_id(client, headers)
    activate_paid_plan(db_session, org, PLANS["team"])
    _expire(db_session, org, days_ago=GRACE_DAYS + 1)

    restriction = restriction_for(db_session, org, "business")
    assert restriction is not None and restriction.kind == "unpaid"
    assert restriction.blocking is True

    model = client.get("/api/v1/sample").json()
    refused = client.post("/api/v1/projects", json={"name": "Нельзя", "model": model},
                          headers=headers)
    assert refused.status_code == 403 and "не оплачена" in refused.json()["detail"]

    # Но данные не конфискованы: просмотр, расчёт и выгрузка открыты (правило B2).
    assert client.get("/api/v1/projects", headers=headers).status_code == 200


def test_the_warning_reaches_the_list_of_organizations(client, register, db_session):
    headers = register()
    org = _org_id(client, headers)
    activate_paid_plan(db_session, org, PLANS["team"])
    _expire(db_session, org, days_ago=2)

    body = client.get("/api/v1/organizations", headers=headers).json()[0]
    grace = [r for r in body["restrictions"] if r["kind"] == "grace"]
    assert len(grace) == 1 and grace[0]["blocking"] is False


def test_paying_again_ends_the_restriction(client, register, db_session):
    """Выход назван в тексте отказа — и он обязан работать."""
    headers = register()
    org = _org_id(client, headers)
    activate_paid_plan(db_session, org, PLANS["team"])
    _expire(db_session, org, days_ago=GRACE_DAYS + 5)
    assert restriction_for(db_session, org, "business") is not None

    activate_paid_plan(db_session, org, PLANS["team"])
    assert restriction_for(db_session, org, "business") is None


def test_one_product_expiring_does_not_touch_the_other(client, register, db_session):
    """Подписка своя у каждого продукта: просроченный «Аудит» не имеет отношения к
    оплаченному «Элит»."""
    headers = register()
    org = _org_id(client, headers)
    activate_paid_plan(db_session, org, PLANS["audit_team"])
    _expire(db_session, org, days_ago=GRACE_DAYS + 1, product="audit")

    assert restriction_for(db_session, org, "audit") is not None
    assert restriction_for(db_session, org, "business") is None


# --- Скрипт эксплуатации: след, а не доступ ---

def test_the_script_records_what_the_derivation_already_decided(client, register,
                                                                db_session):
    """Доступ скрипт не решает — он оставляет **след**: вывод состояния отвечает «как
    сейчас» и не отвечает «когда это произошло», а отток — вопрос о переходах."""
    from scripts.expire_subscriptions import overdue_subscriptions

    headers = register()
    org = _org_id(client, headers)
    activate_paid_plan(db_session, org, PLANS["team"])
    _expire(db_session, org, days_ago=GRACE_DAYS + 2)

    now = datetime.now(timezone.utc)
    stale = overdue_subscriptions(db_session, now)
    assert [s.organization_id for s in stale] == [org]

    # Хранимое состояние ещё не тронуто, а ограничение уже действует.
    assert crud.get_subscription(db_session, org, "business").status == "active"
    assert restriction_for(db_session, org, "business").kind == "unpaid"


def test_the_script_is_idempotent(client, register, db_session):
    """Повторный запуск ничего не меняет: отбор идёт по расхождению хранимого с
    выведенным, а после первой записи расхождения нет."""
    from scripts.expire_subscriptions import overdue_subscriptions

    headers = register()
    org = _org_id(client, headers)
    activate_paid_plan(db_session, org, PLANS["team"])
    _expire(db_session, org, days_ago=GRACE_DAYS + 2)

    now = datetime.now(timezone.utc)
    sub = overdue_subscriptions(db_session, now)[0]
    sub.status = "past_due"
    db_session.commit()
    assert overdue_subscriptions(db_session, now) == []


def test_the_script_leaves_a_paid_and_a_free_subscription_alone(client, register,
                                                                db_session):
    from scripts.expire_subscriptions import overdue_subscriptions

    headers = register()
    org = _org_id(client, headers)
    activate_paid_plan(db_session, org, PLANS["team"])          # срок не кончился
    now = datetime.now(timezone.utc)
    assert overdue_subscriptions(db_session, now) == []

    activate_paid_plan(db_session, org, PLANS["free"])          # срока нет вовсе
    assert overdue_subscriptions(db_session, now) == []
