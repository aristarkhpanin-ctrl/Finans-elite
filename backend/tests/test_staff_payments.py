"""Деньги видны оператору: платежи клиента и выручка платформы (ADMIN-PHASE-F, F2).

Таблица `payments` заведена с 6.5b и **не показывалась нигде**: оператор видел, у кого
какой тариф, и не видел, кто заплатил. Сводка B3 считает *оформленные подписки*, а не
выручку, — и честно об этом говорит, но это и есть пробел.

Проверяется обещание, а не форма: в выручку идут **только успешные** платежи, неуспешные
**остаются** в карточке клиента, усечённый список называет свою неполноту, оговорки едут
с числами на экран и в файл, а изоляция платежей держится фильтром — и это перечень-тест,
потому что RLS у таблицы нет намеренно.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import crud


def _staff(client, db_session, register, email="staff@e.ru") -> dict:
    headers = register(email=email, org="Наша платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, email), is_staff=True)
    return headers


def _client_org(client, register, email="client@e.ru", org="ООО «Клиент»") -> tuple:
    headers = register(email=email, org=org)
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return headers, org_id


def _card(client, staff, org_id) -> dict:
    return client.get(f"/api/v1/admin/organizations/{org_id}", headers=staff).json()


def _metrics(client, staff, **params) -> dict:
    return client.get("/api/v1/admin/metrics", params=params, headers=staff).json()


def _pay(db, org_id, *, amount=2900, status="succeeded", plan="team",
         provider="yookassa", when=None):
    payment = crud.create_payment(db, org_id, plan, amount, provider=provider)
    if when is not None:
        payment.created_at = when
    crud.mark_payment(db, payment, status)
    return payment


# --- Платежи в карточке клиента ---

def test_the_card_shows_who_paid(client, register, db_session):
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    _pay(db_session, org_id)

    card = _card(client, staff, org_id)
    assert len(card["payments"]) == 1
    assert card["payments"][0]["amount_rub"] == 2900
    assert card["payments"][0]["status"] == "succeeded"


def test_a_failed_attempt_stays_in_the_list(client, register, db_session):
    """Попытка оплаты — это разговор с клиентом («карта не прошла»), и спрятать её
    значило бы убрать половину причин, по которым он звонит."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    _pay(db_session, org_id, status="canceled")

    card = _card(client, staff, org_id)
    assert [p["status"] for p in card["payments"]] == ["canceled"]


def test_a_truncated_list_names_its_incompleteness(client, register, db_session):
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    for _ in range(crud.MAX_ORG_PAYMENTS + 3):
        _pay(db_session, org_id)

    card = _card(client, staff, org_id)
    assert len(card["payments"]) == crud.MAX_ORG_PAYMENTS
    assert card["payments_total"] == crud.MAX_ORG_PAYMENTS + 3


def test_payments_of_another_client_are_not_visible(client, register, db_session):
    staff = _staff(client, db_session, register)
    _o1, mine = _client_org(client, register)
    _o2, theirs = _client_org(client, register, email="alien@e.ru", org="Чужая")
    _pay(db_session, theirs, amount=99999)

    assert _card(client, staff, mine)["payments"] == []
    assert len(_card(client, staff, theirs)["payments"]) == 1


def test_an_invoice_paid_through_the_operator_is_visible_as_manual(client, register,
                                                                    db_session):
    """Оплата по счёту (F1) иначе не попала бы в платежи вовсе, и «кто заплатил»
    отвечало бы только про ЮKassa."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    client.post(f"/api/v1/admin/organizations/{org_id}/subscription",
                json={"plan_code": "team", "months": 2}, headers=staff)

    card = _card(client, staff, org_id)
    assert card["payments"][0]["provider"] == "manual"
    assert card["payments"][0]["amount_rub"] == 2900 * 2


# --- Выручка платформы ---

def test_only_successful_payments_are_revenue(client, register, db_session):
    """`pending` — это ещё не деньги, `canceled` — уже не деньги."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    _pay(db_session, org_id, amount=2900)
    _pay(db_session, org_id, amount=9900, status="pending")
    _pay(db_session, org_id, amount=24000, status="canceled")

    revenue = _metrics(client, staff)["revenue"]
    assert sum(p["rub"] for p in revenue) == 2900
    assert sum(p["payments"] for p in revenue) == 1


def test_every_month_of_the_window_stays_in_the_row(client, register, db_session):
    """Пропущенный месяц читается как потерянные данные, а ноль в нём — это ответ."""
    staff = _staff(client, db_session, register)
    revenue = _metrics(client, staff, months=6)["revenue"]
    assert len(revenue) == 6 and all(p["rub"] == 0 for p in revenue)


def test_payments_older_than_the_window_do_not_leak_in(client, register, db_session):
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    _pay(db_session, org_id, amount=5000,
         when=datetime.now(timezone.utc) - timedelta(days=400))
    _pay(db_session, org_id, amount=2900)

    revenue = _metrics(client, staff, months=3)["revenue"]
    assert sum(p["rub"] for p in revenue) == 2900


def test_the_caveats_travel_with_the_numbers(client, register, db_session):
    """Таблица, доехавшая до чужой презентации без оговорок, утверждает больше, чем
    платформа измеряла."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    _pay(db_session, org_id)

    notes = " ".join(_metrics(client, staff)["notes"])
    assert "деньги, пришедшие в месяце" in notes
    assert "возвратов платформа не учитывает" in notes
    assert "по запросу" in notes


def test_an_empty_revenue_explains_itself(client, register, db_session):
    """Ноль должен читаться как «денег не приходило», а не как «не считали»."""
    staff = _staff(client, db_session, register)
    notes = " ".join(_metrics(client, staff)["notes"])
    assert "денег не приходило" in notes
    assert "прямые переводы мимо продукта" in notes


def test_revenue_reaches_the_file_too(client, register, db_session):
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    _pay(db_session, org_id, amount=2900)

    text = client.get("/api/v1/admin/metrics.csv",
                      headers=staff).content.decode("utf-8-sig")
    assert "Месяц;Выручка, ₽;Платежей" in text
    assert ";2900;1" in text


# --- Изоляция платежей ---

def test_only_a_platform_operator_sees_payments(client, register, db_session):
    owner, org_id = _client_org(client, register)
    assert client.get(f"/api/v1/admin/organizations/{org_id}",
                      headers=owner).status_code == 403


#: Чтения платежей **без** фильтра по организации — каждое с причиной.
#:
#: Их ровно два, и оба не про данные одной организации:
#:
#: * ``get_payment_by_provider_id`` — разбор вебхука. Провайдер знает только свой
#:   идентификатор платежа; организация **выводится из найденной строки**, и спросить
#:   её заранее не у кого;
#: * ``revenue_by_month`` — выручка **платформы**. Это взгляд платформы на себя, а не
#:   чтение чужих данных: числа сворачиваются в помесячные итоги и по организациям не
#:   раскладываются.
PLATFORM_WIDE_READS = {"get_payment_by_provider_id", "revenue_by_month"}


def test_every_read_of_payments_filters_by_organization():
    """Перечень-тест. RLS-политики у `payments` нет **намеренно**: вебхук провайдера
    знает только свой идентификатор платежа и не может назвать организацию, а под
    `FORCE ROW LEVEL SECURITY` такое чтение вернуло бы пустоту и молча потеряло бы
    оплату; политика с лазейкой дала бы контур, в котором RLS не действует.

    Значит изоляцию держит фильтр, и он обязан стоять **в каждом** чтении платежей
    организации. Исключения перечислены выше — и новое обязано пройти через этот
    список, а не появиться тихо.
    """
    import ast
    import inspect

    from app import crud as crud_mod
    from app import metrics as metrics_mod

    unfiltered = set()
    for module in (crud_mod, metrics_mod):
        source = inspect.getsource(module)
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.get_source_segment(source, node) or ""
            if "select(Payment)" not in body:
                continue
            if "Payment.organization_id" not in body:
                unfiltered.add(node.name)
    assert unfiltered == PLATFORM_WIDE_READS, unfiltered


def test_the_payments_table_has_no_rls_policy_and_that_is_written_down():
    """Решение живёт в модели, а не в чьей-то голове: следующий, кто заметит
    единственную таблицу с `organization_id` без политики, прочтёт причину там же."""
    from app.db_models import Payment

    doc = Payment.__doc__ or ""
    assert "RLS-политики у этой таблицы нет" in doc
    assert "вебхук" in doc.lower() and "лазейкой" in doc
