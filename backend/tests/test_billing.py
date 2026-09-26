"""Тесты тарифов, подписки и контроля квот (6.5a)."""


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _sample(client):
    return client.get("/api/v1/sample").json()


def _upgrade(client, headers, org_id: str, plan_code: str):
    """Поднять тариф **оплатой** — единственной дорогой, которая у клиента есть (F1).

    Раньше тесты поднимали его прямой сменой, и это было не упрощением, а той самой
    дырой: платный тариф выдавался бесплатно и не истекал. Ручной провайдер в тестах
    активирует оплату сразу, так что дорога короткая — но настоящая.
    """
    return client.post(f"/api/v1/organizations/{org_id}/billing/checkout",
                       json={"plan_code": plan_code, "return_url": "http://x"},
                       headers=headers)


def test_list_plans(client):
    codes = {p["code"] for p in client.get("/api/v1/plans").json()}
    assert {"free", "team", "business"} <= codes


def test_new_org_has_free_subscription(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    sub = client.get(f"/api/v1/organizations/{org_id}/subscription", headers=auth_headers).json()
    assert sub["plan_code"] == "free"
    assert sub["used_members"] == 1   # владелец
    assert sub["used_units"] == 0


def test_a_client_cannot_grant_itself_a_paid_plan(client, auth_headers):
    """Право `billing.manage` есть у владельца организации-клиента, и прямая смена была
    способом взять платный тариф бесплатно и навсегда — срок при ней не ставился вовсе
    (F1). Платный тариф включается **оплатой**."""
    org_id = _org_id(client, auth_headers)
    r = client.post(f"/api/v1/organizations/{org_id}/subscription",
                    json={"plan_code": "team"}, headers=auth_headers)
    assert r.status_code == 403
    # Отказ называет **обе** дороги: оплатить самому или получить назначение платформы.
    detail = r.json()["detail"]
    assert "Оплатите" in detail and "по счёту" in detail
    # И тариф не изменился.
    sub = client.get(f"/api/v1/organizations/{org_id}/subscription",
                     headers=auth_headers).json()
    assert sub["plan_code"] == "free"


def test_a_client_may_step_down_to_free_itself(client, auth_headers):
    """Уйти на бесплатный — отказ от услуги, а не её получение: это решение клиента."""
    org_id = _org_id(client, auth_headers)
    assert _upgrade(client, auth_headers, org_id, "team").status_code == 200

    r = client.post(f"/api/v1/organizations/{org_id}/subscription",
                    json={"plan_code": "free"}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["plan_code"] == "free"
    # Чужой срок не тащится за организацией на бесплатный тариф.
    assert r.json()["current_period_end"] is None


def test_paying_gives_the_plan_and_starts_the_clock(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    assert _upgrade(client, auth_headers, org_id, "team").status_code == 200
    sub = client.get(f"/api/v1/organizations/{org_id}/subscription",
                     headers=auth_headers).json()
    assert sub["plan_code"] == "team" and sub["max_units"] == 50
    # Оплата **начинает отсчёт**: тариф, который не истекает, за деньги не продают.
    assert sub["current_period_end"] is not None


def test_change_plan_invalid_422(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    r = client.post(f"/api/v1/organizations/{org_id}/subscription",
                    json={"plan_code": "gold"}, headers=auth_headers)
    assert r.status_code == 422


def test_non_owner_cannot_change_plan(client, register):
    owner = register("owner@e.ru", "Owner Org")
    org_id = client.post("/api/v1/organizations", json={"name": "Команда"}, headers=owner).json()["id"]
    viewer = register("v@e.ru", "personal")
    client.post(f"/api/v1/organizations/{org_id}/members",
                json={"email": "v@e.ru", "role": "viewer"}, headers={**owner, "X-Organization-Id": org_id})
    vh = {**viewer, "X-Organization-Id": org_id}
    r = client.post(f"/api/v1/organizations/{org_id}/subscription",
                    json={"plan_code": "team"}, headers=vh)
    assert r.status_code == 403


def test_project_quota_enforced(client, auth_headers):
    sample = _sample(client)
    for i in range(5):  # тариф free: 5 проектов
        assert client.post("/api/v1/projects", json={"name": f"P{i}", "model": sample},
                           headers=auth_headers).status_code == 201
    # шестой превышает лимит
    r = client.post("/api/v1/projects", json={"name": "P5", "model": sample}, headers=auth_headers)
    assert r.status_code == 402


def test_quota_lifted_after_upgrade(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    sample = _sample(client)
    for i in range(5):
        client.post("/api/v1/projects", json={"name": f"P{i}", "model": sample}, headers=auth_headers)
    assert client.post("/api/v1/projects", json={"name": "over", "model": sample},
                       headers=auth_headers).status_code == 402
    # апгрейд на team снимает лимит
    _upgrade(client, auth_headers, org_id, "team")
    assert client.post("/api/v1/projects", json={"name": "ok", "model": sample},
                       headers=auth_headers).status_code == 201


def test_member_quota_enforced(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    h = auth_headers  # владелец уже 1 участник; лимит free = 5
    for i in range(4):  # добавляем до 5 участников
        assert client.post(f"/api/v1/organizations/{org_id}/members",
                           json={"email": f"u{i}@e.ru", "role": "viewer"}, headers=h).status_code == 201
    # шестой участник превышает лимит
    r = client.post(f"/api/v1/organizations/{org_id}/members",
                    json={"email": "extra@e.ru", "role": "viewer"}, headers=h)
    assert r.status_code == 402


# --- Тарифы по продуктам (каталог свой у «Элит» и у «Аудита») ---

def _org(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _case(client, headers, name="ООО «Цель»"):
    model = {"name": name, "currency": "RUB", "industry": "",
             "periods": [{"label": "2024", "kind": "year"}],
             "balance": {"A_CASH": ["10"], "P_EQUITY": ["10"]}, "income": {}}
    return client.post("/api/v1/audit/subjects",
                       json={"name": name, "model": model}, headers=headers)


def test_catalog_split_by_product(client):
    """Каталог фильтруется по продукту, и у каждого тарифа он назван."""
    all_plans = client.get("/api/v1/plans").json()
    assert {p["product"] for p in all_plans} == {"business", "audit"}

    audit = client.get("/api/v1/plans?product=audit").json()
    assert {p["code"] for p in audit} == {"audit_trial", "audit_team", "audit_corp"}
    assert all(p["unit_name"] == "дел" for p in audit)

    business = client.get("/api/v1/plans?product=business").json()
    # прайс «Элит» не тронут разделением
    assert {p["code"] for p in business} == {"free", "team", "business"}
    assert next(p for p in business if p["code"] == "team")["price_rub"] == 2900


def test_price_on_request_is_not_zero_price(client):
    """«По запросу» — отдельный признак, а не цена 0.

    Ноль вместо корпоративных условий выглядел бы на экране как бесплатный тариф.
    """
    corp = next(p for p in client.get("/api/v1/plans?product=audit").json()
                if p["code"] == "audit_corp")
    assert corp["price_on_request"] is True
    trial = next(p for p in client.get("/api/v1/plans?product=audit").json()
                 if p["code"] == "audit_trial")
    assert trial["price_on_request"] is False and trial["price_rub"] == 0


def test_subscriptions_are_independent(client, auth_headers):
    """Смена тарифа одного продукта не трогает другой.

    Ради этого и разделены подписки: иначе покупка «Аудита» переводила бы организацию
    на другой тариф «Элит».
    """
    oid = _org(client, auth_headers)
    subs = {s["product"]: s for s in client.get(
        f"/api/v1/organizations/{oid}/subscriptions", headers=auth_headers).json()}
    assert subs["business"]["plan_code"] == "free"
    assert subs["audit"]["plan_code"] == "audit_trial"

    assert _upgrade(client, auth_headers, oid, "audit_team").status_code == 200

    subs = {s["product"]: s for s in client.get(
        f"/api/v1/organizations/{oid}/subscriptions", headers=auth_headers).json()}
    assert subs["audit"]["plan_code"] == "audit_team"
    assert subs["business"]["plan_code"] == "free"      # «Элит» не тронут


def test_subscription_counts_its_own_units(client, auth_headers):
    """Использование квоты считается по единице своего продукта: дела у «Аудита»."""
    oid = _org(client, auth_headers)
    _case(client, auth_headers)
    _case(client, auth_headers, "ООО «Вторая»")

    audit = client.get(f"/api/v1/organizations/{oid}/subscription?product=audit",
                       headers=auth_headers).json()
    assert audit["used_units"] == 2 and audit["unit_name"] == "дел"

    business = client.get(f"/api/v1/organizations/{oid}/subscription",
                          headers=auth_headers).json()
    assert business["used_units"] == 0     # проектов не заводили


def test_case_quota_is_enforced(client, auth_headers):
    """Дела считаются квотой.

    До разделения тарифов их не считал никто: ensure_project_quota смотрел только
    проекты, а создание дела квоту не вызывало — на любом тарифе дел можно было
    завести сколько угодно.
    """
    oid = _org(client, auth_headers)
    for i in range(5):                                  # предел «Пробного» — 5 дел
        assert _case(client, auth_headers, f"Дело {i}").status_code == 201

    r = _case(client, auth_headers, "Шестое")
    assert r.status_code == 402 and "дел" in r.json()["detail"]

    # выше тариф — можно дальше
    _upgrade(client, auth_headers, oid, "audit_team")
    assert _case(client, auth_headers, "Шестое").status_code == 201


def test_case_quota_covers_duplicate_and_demo(client, auth_headers):
    """Квоту проверяют все пути заведения дела, а не только форма создания."""
    for i in range(4):
        _case(client, auth_headers, f"Дело {i}")
    first = client.get("/api/v1/audit/subjects", headers=auth_headers).json()[0]["id"]

    # пятое — демо; шестое уже не помещается ни дублем, ни демо
    assert client.post("/api/v1/audit/subjects/demo",
                       headers=auth_headers).status_code == 201
    assert client.post(f"/api/v1/audit/subjects/{first}/duplicate",
                       headers=auth_headers).status_code == 402
    assert client.post("/api/v1/audit/subjects/demo",
                       headers=auth_headers).status_code == 402


def test_project_quota_untouched_by_audit_cases(client, auth_headers):
    """Дела не расходуют квоту проектов, а проекты — квоту дел: продукты продаются порознь."""
    for i in range(5):
        _case(client, auth_headers, f"Дело {i}")
    oid = _org(client, auth_headers)
    business = client.get(f"/api/v1/organizations/{oid}/subscription",
                          headers=auth_headers).json()
    assert business["used_units"] == 0 and business["plan_code"] == "free"


def test_a_plan_priced_on_request_is_not_bought_in_the_product(client, auth_headers):
    """Его цена — ноль, и ручной провайдер включал его немедленно и бесплатно, а ЮKassa
    получила бы платёж на 0 ₽ (F1). Условия согласуют вне продукта, назначает платформа.

    Отказ при этом **не обещает заявку**: автоматической заявки в продукте нет, и делать
    вид, что она ушла, хуже, чем сказать «свяжитесь с нами»."""
    org_id = _org_id(client, auth_headers)
    r = _upgrade(client, auth_headers, org_id, "audit_corp")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "назначает его платформа" in detail and "автоматической заявки" in detail

    subs = {s["product"]: s for s in client.get(
        f"/api/v1/organizations/{org_id}/subscriptions", headers=auth_headers).json()}
    assert subs["audit"]["plan_code"] == "audit_trial"
