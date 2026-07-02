"""Тесты персистентности проектов (6.1) в контексте организации (6.2)."""
from decimal import Decimal


def _sample_model(client) -> dict:
    return client.get("/api/v1/sample").json()


def test_create_and_get_project(client, auth_headers):
    r = client.post("/api/v1/projects", json={"name": "Мой проект", "model": _sample_model(client)},
                    headers=auth_headers)
    assert r.status_code == 201
    pid = r.json()["id"]
    got = client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["model"]["header"]["duration_months"] == 12


def test_list_projects(client, auth_headers):
    client.post("/api/v1/projects", json={"name": "A", "model": _sample_model(client)}, headers=auth_headers)
    client.post("/api/v1/projects", json={"name": "B", "model": _sample_model(client)}, headers=auth_headers)
    r = client.get("/api/v1/projects", headers=auth_headers)
    assert {p["name"] for p in r.json()} == {"A", "B"}


def test_get_missing_404(client, auth_headers):
    assert client.get("/api/v1/projects/nope", headers=auth_headers).status_code == 404


def test_update_project(client, auth_headers):
    pid = client.post("/api/v1/projects", json={"name": "Старое", "model": _sample_model(client)},
                      headers=auth_headers).json()["id"]
    r = client.put(f"/api/v1/projects/{pid}", json={"name": "Новое"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Новое"


def test_delete_project(client, auth_headers):
    pid = client.post("/api/v1/projects", json={"name": "Удалить", "model": _sample_model(client)},
                      headers=auth_headers).json()["id"]
    assert client.delete(f"/api/v1/projects/{pid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}", headers=auth_headers).status_code == 404


def test_calculate_stored_project(client, auth_headers):
    pid = client.post("/api/v1/projects", json={"name": "Расчёт", "model": _sample_model(client)},
                      headers=auth_headers).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/calculate", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    b20 = next(l for l in data["balance"]["lines"] if l["code"] == "B20")["values"]
    b34 = next(l for l in data["balance"]["lines"] if l["code"] == "B34")["values"]
    for a, b in zip(b20, b34):
        assert abs(Decimal(a) - Decimal(b)) <= Decimal("0.01")
    # Поля, которые показывает UI результатов: оценка бизнеса и расширенные метрики.
    assert "net_assets" in data["valuation"] and "gordon_value" in data["valuation"]
    assert "pv_investments" in data["metrics"] and "peak_financing_need" in data["metrics"]


def _calc_with_growth(client, auth_headers, g: str) -> dict:
    model = _sample_model(client)
    model["settings"]["terminal_growth_rate"] = g
    pid = client.post("/api/v1/projects", json={"name": f"g={g}", "model": model},
                      headers=auth_headers).json()["id"]
    return client.post(f"/api/v1/projects/{pid}/calculate", headers=auth_headers).json()


def test_terminal_growth_rate_drives_gordon_valuation(client, auth_headers):
    """Темп роста g (вводится в UI) проходит в расчёт и меняет оценку по Гордону."""
    base = _calc_with_growth(client, auth_headers, "0")["valuation"]["gordon_value"]
    grown = _calc_with_growth(client, auth_headers, "0.05")["valuation"]["gordon_value"]
    assert base is not None and grown is not None
    assert Decimal(grown) != Decimal(base)   # g влияет на капитализацию (r−g в знаменателе)


def test_create_invalid_model_422(client, auth_headers):
    bad = {"name": "Плохой", "model": {"header": {"duration_months": 0}}}
    assert client.post("/api/v1/projects", json=bad, headers=auth_headers).status_code == 422


# --- B1: сводка последнего расчёта ---

def test_last_calc_summary_lifecycle(client, auth_headers):
    """Расчёт заполняет сводку; PUT модели делает проект stale, не стирая сводку."""
    pid = client.post("/api/v1/projects", json={"name": "Сводка", "model": _sample_model(client)},
                      headers=auth_headers).json()["id"]

    # До расчёта: сводки нет, проект — черновик.
    fresh = client.get(f"/api/v1/projects/{pid}", headers=auth_headers).json()
    assert fresh["last_calc"] is None and fresh["is_stale"] is True

    calc = client.post(f"/api/v1/projects/{pid}/calculate", headers=auth_headers).json()
    got = client.get(f"/api/v1/projects/{pid}", headers=auth_headers).json()
    lc = got["last_calc"]
    assert lc is not None
    assert Decimal(lc["npv"]) == Decimal(calc["metrics"]["npv"])
    assert lc["engine_version"] == calc["engine_version"]
    assert got["is_stale"] is False

    # Список тоже отдаёт сводку.
    row = next(p for p in client.get("/api/v1/projects", headers=auth_headers).json()
               if p["id"] == pid)
    assert row["last_calc"] is not None and row["is_stale"] is False

    # PUT модели → stale, но сводка сохраняется (карточка показывает старые числа + «Черновик»).
    model = _sample_model(client)
    model["header"]["duration_months"] = 13
    upd = client.put(f"/api/v1/projects/{pid}", json={"model": model}, headers=auth_headers).json()
    assert upd["is_stale"] is True
    assert upd["last_calc"] is not None
    assert Decimal(upd["last_calc"]["npv"]) == Decimal(calc["metrics"]["npv"])


# --- B2: дублирование проекта ---

def test_duplicate_project(client, auth_headers):
    src = client.post("/api/v1/projects", json={"name": "Оригинал", "model": _sample_model(client)},
                      headers=auth_headers).json()
    client.post(f"/api/v1/projects/{src['id']}/calculate", headers=auth_headers)

    r = client.post(f"/api/v1/projects/{src['id']}/duplicate", headers=auth_headers)
    assert r.status_code == 201
    copy = r.json()
    assert copy["name"] == "Оригинал (копия)"
    assert copy["id"] != src["id"]
    assert copy["model"] == src["model"]
    # Сводка расчёта не переносится: копия — черновик.
    assert copy["last_calc"] is None and copy["is_stale"] is True


def test_duplicate_missing_404(client, auth_headers):
    assert client.post("/api/v1/projects/nope/duplicate", headers=auth_headers).status_code == 404


def test_duplicate_respects_project_quota(client, auth_headers):
    """Дубль учитывает квоту тарифа как create (free: 5 проектов → 402)."""
    sample = _sample_model(client)
    first = client.post("/api/v1/projects", json={"name": "P0", "model": sample},
                        headers=auth_headers).json()["id"]
    for i in range(1, 5):
        client.post("/api/v1/projects", json={"name": f"P{i}", "model": sample},
                    headers=auth_headers)
    assert client.post(f"/api/v1/projects/{first}/duplicate",
                       headers=auth_headers).status_code == 402
