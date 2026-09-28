"""Сводка организации на одном экране (ADMIN-PHASE-F, F7).

Администратор видел участников, активность и журнал — и не видел того, что спрашивают
чаще всего: сколько у нас проектов и дел, сколько ещё можно завести, когда кончается
оплаченный период. Ответы были разложены по трём экранам и по отказам, которые
приходили уже в момент сохранения: 402 «кончилась квота» и 403 «не оплачено» — разные
разговоры с разными выходами.

Главный тест здесь — не про экран, а про **совпадение**: «осталось» на сводке считается
тем же, чем отказывает создание, а причина ограничения — теми же словами, какими
отказывает запись. Разойдясь, они дали бы клиенту две правды сразу — «осталось 2» на
экране и отказ на следующем сохранении.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import crud


def _owner(client, register, email="owner@e.ru", org="ООО «Клиент»") -> tuple:
    headers = register(email=email, org=org)
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return headers, org_id


def _overview(client, headers, org_id) -> dict:
    return client.get(f"/api/v1/organizations/{org_id}/overview", headers=headers).json()


def _of(body: dict, product: str) -> dict:
    return next(p for p in body["products"] if p["product"] == product)


def _project(client, headers, name="Проект") -> str:
    return client.post("/api/v1/projects",
                       json={"name": name, "model": client.get("/api/v1/sample").json()},
                       headers=headers).json()["id"]


def _case(client, headers, name="Дело") -> str:
    return client.post("/api/v1/audit/subjects", json={"name": name, "model": {
        "name": name, "periods": [], "lines": []}}, headers=headers).json()["id"]


# --- Объёмы и квоты ---

def test_the_overview_answers_what_is_in_the_organization(client, register):
    owner, org_id = _owner(client, register)
    _project(client, owner)
    _case(client, owner)

    body = _overview(client, owner, org_id)
    assert body["name"] == "ООО «Клиент»"
    assert body["projects"] == 1 and body["cases"] == 1 and body["members"] == 1


def test_the_quota_left_matches_what_creation_refuses(client, register, db_session):
    """Главное обещание сводки. Посчитай она «осталось» сама — и однажды показала бы
    «осталось 2» там, где сохранение уже отвечает 402."""
    owner, org_id = _owner(client, register)
    limit = _of(_overview(client, owner, org_id), "business")["units_limit"]

    for i in range(limit):
        assert client.post("/api/v1/projects",
                           json={"name": f"П{i}",
                                 "model": client.get("/api/v1/sample").json()},
                           headers=owner).status_code == 201

    business = _of(_overview(client, owner, org_id), "business")
    assert business["units_used"] == limit
    assert business["units_left"] == 0
    # И ровно здесь создание отказывает — числа сходятся с поведением, а не друг с другом.
    assert client.post("/api/v1/projects",
                       json={"name": "Лишний",
                             "model": client.get("/api/v1/sample").json()},
                       headers=owner).status_code == 402


def test_each_product_counts_its_own_unit(client, register):
    """Квота «Элита» меряется проектами, «Аудита» — делами: завести дело не должно
    съедать место под проект."""
    owner, org_id = _owner(client, register)
    _project(client, owner)

    body = _overview(client, owner, org_id)
    assert _of(body, "business")["units_used"] == 1
    assert _of(body, "audit")["units_used"] == 0
    assert _of(body, "business")["unit_name"] == "проектов"
    assert _of(body, "audit")["unit_name"] == "дел"


def test_no_limit_is_not_zero(client, register, db_session):
    """У корпоративного тарифа квоты нет вовсе. Ноль здесь читался бы как «ничего
    нельзя» ровно там, где можно всё."""
    owner, org_id = _owner(client, register)
    crud.set_plan(db_session, org_id, "business", product="business")

    business = _of(_overview(client, owner, org_id), "business")
    assert business["units_limit"] is None
    assert business["units_left"] is None
    assert any("не ноль" in n for n in _overview(client, owner, org_id)["notes"])


# --- Срок подписки ---

def test_a_subscription_without_a_period_does_not_expire(client, register):
    """`None` — это «не истекает», а не «истёк давно»: у бесплатного периода нет."""
    owner, org_id = _owner(client, register)
    business = _of(_overview(client, owner, org_id), "business")

    assert business["period_end"] is None
    assert business["days_left"] is None
    assert business["grace_left"] is None


def test_the_days_left_are_a_number_not_soon(client, register, db_session):
    """«Осталось 12 дней» человек кладёт в календарь, «скоро» — нет."""
    owner, org_id = _owner(client, register)
    sub = crud.get_subscription(db_session, org_id, "business")
    sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=12, hours=1)
    db_session.commit()

    assert _of(_overview(client, owner, org_id), "business")["days_left"] == 12


def test_the_grace_period_is_visible_and_counted(client, register, db_session):
    """Льготный срок настоящий: организация работает, а клиент предупреждён — числом."""
    owner, org_id = _owner(client, register)
    sub = crud.get_subscription(db_session, org_id, "business")
    sub.current_period_end = datetime.now(timezone.utc) - timedelta(days=3)
    db_session.commit()

    business = _of(_overview(client, owner, org_id), "business")
    assert business["days_left"] == 0
    assert business["grace_left"] == 11          # 14 − 3
    assert business["restriction_kind"] == "grace"
    assert business["restriction_blocking"] is False


def test_the_restriction_speaks_the_same_words_as_the_refusal(client, register,
                                                              db_session):
    """Второй источник этой правды разошёлся бы с первым, и клиент видел бы спокойный
    экран, на котором ничего не сохраняется."""
    owner, org_id = _owner(client, register)
    sub = crud.get_subscription(db_session, org_id, "business")
    sub.current_period_end = datetime.now(timezone.utc) - timedelta(days=30)
    db_session.commit()

    business = _of(_overview(client, owner, org_id), "business")
    assert business["restriction_kind"] == "unpaid"
    assert business["restriction_blocking"] is True
    assert business["status"] == "past_due"      # выведено, а не прочитано из поля

    # Неоплата закрывает **право** на запись, а не квоту: 403 с той же причиной, а не
    # 402 «купите больше места» — это разные разговоры и разные выходы.
    refusal = client.post("/api/v1/projects",
                          json={"name": "П", "model": client.get("/api/v1/sample").json()},
                          headers=owner)
    assert refusal.status_code == 403
    assert business["restriction_reason"] in refusal.json()["detail"]


def test_a_subscription_never_taken_is_named_so(client, register):
    """«Не оформляли» и «оформили бесплатный» — разные состояния и разные разговоры."""
    owner, org_id = _owner(client, register)
    assert _of(_overview(client, owner, org_id), "audit")["status"] == "none"


# --- Оговорки ---

def test_the_platform_does_not_invent_a_calculation_count(client, register):
    owner, org_id = _owner(client, register)
    _project(client, owner)
    body = _overview(client, owner, org_id)

    assert body["last_calculated_at"] is None
    assert any("счётчика расчётов нет" in n for n in body["notes"])
    assert any("ещё не считали" in n for n in body["notes"])


def test_a_member_without_a_mark_is_unknown_not_idle(client, register):
    owner, org_id = _owner(client, register)
    client.post(f"/api/v1/organizations/{org_id}/members",
                json={"email": "invited@e.ru", "full_name": "П", "role": "analyst"},
                headers=owner)

    body = _overview(client, owner, org_id)
    assert body["members_unknown"] == 1
    assert any("«неизвестно», а не «не работает»" in n for n in body["notes"])


def test_a_suspended_member_still_holds_a_seat(client, register, db_session):
    """Иначе администратор приостанавливает сотрудника, ждёт свободного места и не
    понимает, почему его нет."""
    owner, org_id = _owner(client, register)
    client.post(f"/api/v1/organizations/{org_id}/members",
                json={"email": "invited@e.ru", "full_name": "П", "role": "analyst"},
                headers=owner)
    victim = crud.get_user_by_email(db_session, "invited@e.ru")
    client.post(f"/api/v1/organizations/{org_id}/members/{victim.id}/block",
                json={"reason": "отпуск"}, headers=owner)

    body = _overview(client, owner, org_id)
    assert body["members_blocked"] == 1
    assert _of(body, "business")["members_left"] == \
        _of(body, "business")["members_limit"] - body["members"]
    assert any("место в квоте" in n for n in body["notes"])


# --- Доступ и изоляция ---

def test_every_member_sees_the_overview(client, register):
    """«Почему я не могу завести проект» — вопрос того, кто упёрся, а не только того,
    кто платит. Имён здесь нет, только числа."""
    owner, org_id = _owner(client, register)
    analyst = register(email="analyst@e.ru", org="Личная")
    client.post(f"/api/v1/organizations/{org_id}/members",
                json={"email": "analyst@e.ru", "full_name": "А", "role": "analyst"},
                headers=owner)

    r = client.get(f"/api/v1/organizations/{org_id}/overview",
                   headers={**analyst, "X-Organization-Id": org_id})
    assert r.status_code == 200 and r.json()["projects"] == 0


def test_an_outsider_sees_nothing(client, register):
    _headers, org_id = _owner(client, register)
    alien = register(email="alien@e.ru", org="Чужая")
    assert client.get(f"/api/v1/organizations/{org_id}/overview",
                      headers=alien).status_code == 403


def test_the_overview_does_not_leak_names(client, register):
    """Сводка — числа, а не содержимое: названий проектов и дел в ней нет."""
    owner, org_id = _owner(client, register)
    _project(client, owner, name="Покупка завода в Твери")
    _case(client, owner, name="Цель поглощения")

    text = client.get(f"/api/v1/organizations/{org_id}/overview", headers=owner).text
    assert "Покупка завода" not in text and "Цель поглощения" not in text


# --- Перечень: у каждого продукта своя мера квоты ---

def test_every_product_has_its_unit_counter():
    """Перечень-тест. Продукт без своей меры получил бы «израсходовано 0» и «осталось
    всё» — то есть сводка обещала бы место, которого нет, а создание отказывало.
    """
    from app.billing import UNIT_COUNT
    from app.plans import PRODUCTS

    assert set(UNIT_COUNT) == set(PRODUCTS), (
        "у каждого продукта должна быть своя мера квоты: " + str(set(UNIT_COUNT) ^ set(PRODUCTS)))


def test_the_quota_check_and_the_overview_read_the_same_counter():
    """Одна карта на проверку и на показ — не ради краткости, а чтобы два ответа на
    вопрос «можно ли завести ещё» не разошлись."""
    import inspect

    from app import billing

    for name in ("ensure_project_quota", "ensure_case_quota"):
        assert "units_used" in inspect.getsource(getattr(billing, name)), name
    assert "billing.units_used" in inspect.getsource(
        __import__("app.overview", fromlist=["build_overview"]).build_overview)
