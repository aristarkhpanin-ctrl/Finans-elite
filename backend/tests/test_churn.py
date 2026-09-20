"""Метрика оттока (ADMIN-PHASE-F, F8).

Определение записано заранее и здесь не переизобретается (OPEN-DECISIONS §1): отток —
организация, у которой **была платная** подписка и не стало; триал, не ставший платным, —
воронка, а не отток.

Проверяется не арифметика, а обещания, ради которых пункт и стоял последним:

* **«Не измеряется» — не ноль.** Запись об окончании оплаченного периода оставляет скрипт
  эксплуатации; пока его не запускали, ноль ушедших означал бы «никто не уходит».
* **Две картины не сводятся в одно число.** Журнал отвечает «что записано как
  случившееся», платежи — «кто платил и перестал»; доля считается внутри платежей.
* **Прежний тариф назван в самой записи.** Без него «сменил тариф на бесплатный» не
  отличается от «переключил бесплатный на бесплатный», и отток пришлось бы угадывать.
* **Единица одна — организация.** Иначе картины считали бы разное и перестали бы быть
  сравнимыми.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import crud
from app.billing import parse_plan_change, plan_change_details
from app.billing_period import GRACE_DAYS, PERIOD_DAYS
from app.database import as_tenant
from app.metrics import _months_back


def _staff(client, db_session, register, email="staff@e.ru") -> dict:
    headers = register(email=email, org="Наша платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, email), is_staff=True)
    return headers


def _client_org(client, register, email="client@e.ru", org="ООО «Клиент»") -> tuple:
    headers = register(email=email, org=org)
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return headers, org_id


def _churn(client, staff, **params) -> dict:
    return client.get("/api/v1/admin/metrics", params=params,
                      headers=staff).json()["churn"]


def _notes(client, staff, **params) -> list[str]:
    return client.get("/api/v1/admin/metrics", params=params,
                      headers=staff).json()["notes"]


def _month_of(when: datetime) -> str:
    return f"{when.year:04d}-{when.month:02d}"


def _point(churn: dict, month: str) -> dict:
    return next(p for p in churn["months"] if p["month"] == month)


def _pay(db, org_id, *, when, amount=2900, plan="team", status="succeeded"):
    """Успешный платёж заданной датой — вторая картина оттока целиком из них."""
    payment = crud.create_payment(db, org_id, plan, amount, provider="yookassa")
    crud.mark_payment(db, payment, status)
    payment.created_at = when
    db.commit()
    return payment


def _subscribed(db, org_id, *, period_end, plan="team"):
    """Подписка с концом оплаченного периода: именно по ней видно, платят ли сейчас."""
    return crud.set_plan(db, org_id, plan, product="business",
                         period_end=period_end, paid=True)


def _journal(db, org_id, action, *, when, details="", name="team"):
    """Запись журнала нужной датой. Журнал под RLS — заходим той же дверью, что и всё."""
    with as_tenant(db, org_id):
        entry = crud.log_action(db, org_id, None, action, entity_type="organization",
                                entity_id=org_id, entity_name=name, details=details)
        entry.created_at = when
        db.commit()
    return entry


# --- «Не измеряется» вместо нуля ---

def test_expiry_is_not_measured_until_the_script_has_run(client, db_session, register):
    """Скрипт эксплуатации не запускали — значит уход по окончании периода **неизвестен**.

    Это главная оговорка пункта: приложение таких записей не делает вовсе, и ноль на
    экране читался бы как «никто не уходит» — утверждение, которого платформа не делала.
    """
    staff = _staff(client, db_session, register)
    _client_org(client, register)

    churn = _churn(client, staff)
    assert churn["expiry_logged"] is False
    assert all(point["expired"] is None for point in churn["months"])
    assert any("не измеряется" in note and "expire_subscriptions" in note
               for note in _notes(client, staff))


def test_months_before_the_first_record_stay_unmeasured(client, db_session, register):
    """Скрипт запустили в этом месяце — прошлые месяцы он не застал.

    Ноль за месяц, которого запись не застала, — тот же обман, что и ноль до первого
    запуска, только менее заметный.
    """
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    _journal(db_session, org_id, "billing.overdue", when=now)

    churn = _churn(client, staff, months=6)
    assert churn["expiry_logged"] is True
    assert _point(churn, _month_of(now))["expired"] == 1
    earlier = _months_back(now, 6)[0]
    assert _point(churn, earlier)["expired"] is None


def test_silence_after_the_first_record_is_a_measured_zero(client, db_session, register):
    """А вот после первой записи ноль — уже измеренный ноль, и прочерк был бы ложью
    в другую сторону: «не знаем» там, где знаем."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    _journal(db_session, org_id, "billing.overdue", when=now - timedelta(days=70))

    churn = _churn(client, staff, months=6)
    assert _point(churn, _month_of(now))["expired"] == 0


# --- Прежний тариф в записи журнала ---

def test_the_journal_names_the_plan_left_behind(client, register, db_session):
    """Запись о смене тарифа называет, **с чего** ушли, — как смена роли участника.

    Без прежнего тарифа уход с платного не отличается от переключения бесплатного на
    бесплатный, и отток по журналу считался бы догадками.
    """
    headers, org_id = _client_org(client, register)
    client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                json={"plan_code": "team", "return_url": "http://x"}, headers=headers)
    client.post(f"/api/v1/organizations/{org_id}/subscription",
                json={"plan_code": "free"}, headers=headers)

    page = client.get(f"/api/v1/organizations/{org_id}/audit-log", headers=headers).json()
    entry = next(e for e in page["entries"] if e["action"] == "billing.plan_change")
    assert parse_plan_change(entry["details"]) == ("business", "team", "free")


def test_the_format_is_written_and_read_by_one_pair(client, register):
    """Строку пишет и читает одна пара функций: разъехавшись, они молча обнулили бы
    отток по журналу — записи остались бы, а читаться перестали."""
    assert parse_plan_change(plan_change_details("audit", "audit_pro", "audit_trial")) \
        == ("audit", "audit_pro", "audit_trial")
    # Старый формат (до F8) — один продукт: прежний тариф не назван, и это видно.
    assert parse_plan_change("business") is None


def test_leaving_a_paid_plan_counts_as_churn(client, db_session, register):
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    _journal(db_session, org_id, "billing.plan_change", when=now,
             details=plan_change_details("business", "team", "free"))

    assert _point(_churn(client, staff), _month_of(now))["downgraded"] == 1


def test_switching_between_free_plans_is_not_churn(client, db_session, register):
    """Организация, которая не платила, уйти с платного не может: это воронка, а не отток."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    _journal(db_session, org_id, "billing.plan_change", when=now,
             details=plan_change_details("audit", "audit_trial", "free"))

    assert _point(_churn(client, staff), _month_of(now))["downgraded"] == 0


def test_moving_between_paid_plans_is_not_churn(client, db_session, register):
    """Понижение с «Корпоративного» на «Команду» — не уход: клиент остался платящим."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    _journal(db_session, org_id, "billing.plan_change", when=now,
             details=plan_change_details("business", "business_corp", "team"))

    assert _point(_churn(client, staff), _month_of(now))["downgraded"] == 0


def test_a_record_without_the_former_plan_is_not_guessed(client, db_session, register):
    """Запись, сделанная до F8, прежнего тарифа не называет — и метрика **не гадает**.

    Ноль сказал бы «никто не уходил сам», а правда — «по этим записям не видно». Число
    таких записей названо отдельно: молчание о них читалось бы как их отсутствие.
    """
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    _journal(db_session, org_id, "billing.plan_change", when=now, details="business")

    churn = _churn(client, staff)
    assert churn["unnamed_plan_changes"] == 1
    assert _point(churn, _month_of(now))["downgraded"] is None
    assert any("прежний тариф не назван" in note for note in _notes(client, staff))


def test_one_readable_record_still_gives_a_number(client, db_session, register):
    """Месяц со смешанными записями показывает число по читаемым, а не прочерк: нижняя
    граница полезнее отказа, если сказано, что она нижняя."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    _journal(db_session, org_id, "billing.plan_change", when=now, details="business")
    _journal(db_session, org_id, "billing.plan_change", when=now,
             details=plan_change_details("business", "team", "free"))

    churn = _churn(client, staff)
    assert _point(churn, _month_of(now))["downgraded"] == 1
    assert churn["unnamed_plan_changes"] == 1


# --- Единица счёта: организация ---

def test_churn_counts_organizations_not_subscriptions(client, db_session, register):
    """Клиент, просрочивший оба продукта в один месяц, потерян **один раз**.

    Сложив строки, платформа потеряла бы одного клиента дважды — и картина по журналу
    перестала бы быть сравнимой с картиной по платежам, где платёж один на организацию.
    """
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    _journal(db_session, org_id, "billing.overdue", when=now, name="team")
    _journal(db_session, org_id, "billing.overdue", when=now, name="audit_pro")

    assert _point(_churn(client, staff), _month_of(now))["expired"] == 1


# --- Картина 2: платил и перестал ---

def test_a_payer_who_stopped_is_dated_by_the_last_payment(client, db_session, register):
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    paid_at = now - timedelta(days=PERIOD_DAYS + GRACE_DAYS + 40)
    _pay(db_session, org_id, when=paid_at)
    _subscribed(db_session, org_id, period_end=paid_at + timedelta(days=PERIOD_DAYS))

    point = _point(_churn(client, staff, months=12), _month_of(paid_at))
    assert point["payers"] == 1 and point["stopped"] == 1
    assert point["rate"] == 1.0


def test_a_payer_inside_the_paid_period_has_not_left(client, db_session, register):
    """Внутри оплаченного периода ушедших нет: «давно платил» и «перестал платить» —
    разные утверждения, и второе проверяется подпиской, а не календарём от платежа.

    Так же ведёт себя оплата за несколько периодов сразу (оплата по счёту): числа
    месяцев в платеже нет, зато конец периода его уже учёл.
    """
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    paid_at = now - timedelta(days=200)
    _pay(db_session, org_id, when=paid_at)
    _subscribed(db_session, org_id, period_end=now + timedelta(days=160))

    point = _point(_churn(client, staff, months=12), _month_of(paid_at))
    assert point["payers"] == 1 and point["stopped"] == 0
    assert point["rate"] == 0.0


def test_grace_period_is_not_yet_a_departure(client, db_session, register):
    """Льготный срок настоящий (B2): пока он идёт, организация работает как обычно —
    и ушедшей её называть рано."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    paid_at = now - timedelta(days=PERIOD_DAYS + 2)
    _pay(db_session, org_id, when=paid_at)
    _subscribed(db_session, org_id, period_end=now - timedelta(days=2))

    assert _point(_churn(client, staff), _month_of(paid_at))["stopped"] == 0


def test_a_failed_payment_is_not_a_payer(client, db_session, register):
    """`pending` — ещё не деньги, `canceled` — уже не деньги (то же правило, что в
    выручке): организация, чей платёж не прошёл, плательщиком месяца не была."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    _pay(db_session, org_id, when=now, status="canceled")

    assert _point(_churn(client, staff), _month_of(now))["payers"] == 0


def test_rate_is_a_dash_without_payers(client, db_session, register):
    """Делить не на что — прочерк, а не ноль процентов: «никто не ушёл» и «никого не
    было» выглядели бы одинаково."""
    staff = _staff(client, db_session, register)
    _client_org(client, register)

    assert all(point["rate"] is None for point in _churn(client, staff)["months"])


def test_the_two_pictures_stay_apart(client, db_session, register):
    """Уход, записанный журналом, доли по платежам не трогает — и наоборот.

    Смысл пункта: у картин разные пропуски, и частное от деления одной на другую не
    значило бы ничего.
    """
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    now = datetime.now(timezone.utc)
    _journal(db_session, org_id, "billing.overdue", when=now)

    point = _point(_churn(client, staff), _month_of(now))
    assert point["expired"] == 1
    assert point["payers"] == 0 and point["stopped"] == 0 and point["rate"] is None
    assert any("не сводятся в одно число" in note for note in _notes(client, staff))


# --- Оговорки ---

def test_notes_name_what_the_numbers_miss(client, db_session, register):
    """Оговорки едут с числами, а не остаются в документации: неназванный пробел
    читается как благополучие."""
    staff = _staff(client, db_session, register)
    notes = " ".join(_notes(client, staff))
    assert "воронка, а не отток" in notes            # определение названо вслух
    assert "организациями, а не подписками" in notes  # единица счёта
    assert "закрывшая себя" in notes                  # ушедших совсем не видно ни в одной
    assert "последнего платежа" in notes              # чем датирован уход по платежам


def test_the_csv_says_unmeasured_in_words(client, db_session, register):
    """В файле «не измеряется» — слово, а не пустая ячейка: чем дальше таблица уехала от
    экрана, тем увереннее пустота читается как ноль."""
    staff = _staff(client, db_session, register)
    _client_org(client, register)

    body = client.get("/api/v1/admin/metrics.csv", headers=staff).content.decode("utf-8-sig")
    assert "Не продлили" in body and "Ушли на бесплатный" in body
    assert "не измеряется" in body
