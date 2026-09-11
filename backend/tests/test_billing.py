"""Тесты тарифов, подписки и контроля квот (6.5a)."""


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _sample(client):
    return client.get("/api/v1/sample").json()


def test_list_plans(client):
    codes = {p["code"] for p in client.get("/api/v1/plans").json()}
    assert {"free", "team", "business"} <= codes


def test_new_org_has_free_subscription(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    sub = client.get(f"/api/v1/organizations/{org_id}/subscription", headers=auth_headers).json()
    assert sub["plan_code"] == "free"
    assert sub["used_members"] == 1   # владелец
    assert sub["used_units"] == 0


def test_change_plan_owner(client, auth_headers):
    org_id = _org_id(client, auth_headers)
    r = client.post(f"/api/v1/organizations/{org_id}/subscription",
                    json={"plan_code": "team"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["plan_code"] == "team"
    assert r.json()["max_units"] == 50


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
    client.post(f"/api/v1/organizations/{org_id}/subscription",
                json={"plan_code": "team"}, headers=auth_headers)
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

    r = client.post(f"/api/v1/organizations/{oid}/subscription",
                    json={"plan_code": "audit_team"}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["product"] == "audit"

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
    client.post(f"/api/v1/organizations/{oid}/subscription",
                json={"plan_code": "audit_team"}, headers=auth_headers)
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
