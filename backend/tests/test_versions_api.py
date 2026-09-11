"""Тесты API версий проекта (пакет №8, gap 4.4, V1): снимок/список/диф/восстановление."""


def _project(client, headers, name="Версии"):
    sample = client.get("/api/v1/sample").json()
    return client.post("/api/v1/projects", json={"name": name, "model": sample},
                       headers=headers).json()["id"]


def test_create_list_get_version(client, auth_headers):
    pid = _project(client, auth_headers)
    r = client.post(f"/api/v1/projects/{pid}/versions", json={"label": "Базовая"},
                    headers=auth_headers)
    assert r.status_code == 201
    vid = r.json()["id"]
    assert r.json()["label"] == "Базовая"
    assert r.json()["npv"] is not None                  # сводка расчёта посчитана

    lst = client.get(f"/api/v1/projects/{pid}/versions", headers=auth_headers).json()
    assert len(lst) == 1 and lst[0]["id"] == vid

    full = client.get(f"/api/v1/projects/{pid}/versions/{vid}", headers=auth_headers).json()
    assert full["model"]["header"]["name"]              # модель снимка на месте


def test_version_default_label(client, auth_headers):
    """Пустая метка → автогенерируется из времени обновления проекта."""
    pid = _project(client, auth_headers)
    r = client.post(f"/api/v1/projects/{pid}/versions", json={"label": ""},
                    headers=auth_headers)
    assert r.status_code == 201 and r.json()["label"].startswith("Версия от")


def test_diff_against_current(client, auth_headers):
    pid = _project(client, auth_headers)
    vid = client.post(f"/api/v1/projects/{pid}/versions", json={"label": "V1"},
                      headers=auth_headers).json()["id"]
    # меняем рабочую модель: удлиняем горизонт и правим имя
    model = client.get(f"/api/v1/projects/{pid}", headers=auth_headers).json()["model"]
    model["header"]["name"] = "Изменённый"
    client.put(f"/api/v1/projects/{pid}", json={"name": "Изменённый", "model": model},
               headers=auth_headers)

    diff = client.get(f"/api/v1/projects/{pid}/versions/{vid}/diff?against=current",
                      headers=auth_headers).json()
    assert diff["against"] == "current" and diff["base_id"] == vid
    paths = {c["path"]: c for c in diff["model_changes"]}
    assert "header.name" in paths
    assert paths["header.name"]["old"] and paths["header.name"]["new"] == "Изменённый"
    # показатели тоже сравниваются (набор заголовочных)
    assert {c["key"] for c in diff["metric_changes"]} >= {"npv", "irr_annual"}


def test_diff_version_to_version(client, auth_headers):
    pid = _project(client, auth_headers)
    v1 = client.post(f"/api/v1/projects/{pid}/versions", json={"label": "A"},
                     headers=auth_headers).json()["id"]
    model = client.get(f"/api/v1/projects/{pid}", headers=auth_headers).json()["model"]
    model["settings"]["discount_rate_annual"] = "0.25"
    client.put(f"/api/v1/projects/{pid}", json={"name": "Версии", "model": model},
               headers=auth_headers)
    v2 = client.post(f"/api/v1/projects/{pid}/versions", json={"label": "B"},
                     headers=auth_headers).json()["id"]

    diff = client.get(f"/api/v1/projects/{pid}/versions/{v1}/diff?against={v2}",
                      headers=auth_headers).json()
    paths = {c["path"] for c in diff["model_changes"]}
    assert "settings.discount_rate_annual" in paths


def test_restore_version(client, auth_headers):
    pid = _project(client, auth_headers)
    vid = client.post(f"/api/v1/projects/{pid}/versions", json={"label": "Оригинал"},
                      headers=auth_headers).json()["id"]
    model = client.get(f"/api/v1/projects/{pid}", headers=auth_headers).json()["model"]
    model["header"]["name"] = "Черновик"
    client.put(f"/api/v1/projects/{pid}", json={"name": "Черновик", "model": model},
               headers=auth_headers)

    restored = client.post(f"/api/v1/projects/{pid}/versions/{vid}/restore",
                           headers=auth_headers).json()
    assert restored["model"]["header"]["name"] != "Черновик"   # вернулась модель снимка
    assert restored["status"] == "draft"


def test_delete_version(client, auth_headers):
    pid = _project(client, auth_headers)
    vid = client.post(f"/api/v1/projects/{pid}/versions", json={"label": "X"},
                      headers=auth_headers).json()["id"]
    assert client.delete(f"/api/v1/projects/{pid}/versions/{vid}",
                         headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}/versions", headers=auth_headers).json() == []


def test_version_limit(client, auth_headers, monkeypatch):
    from app import crud
    monkeypatch.setattr(crud, "MAX_VERSIONS_PER_PROJECT", 2)
    pid = _project(client, auth_headers)
    for i in range(2):
        assert client.post(f"/api/v1/projects/{pid}/versions", json={"label": f"V{i}"},
                           headers=auth_headers).status_code == 201
    over = client.post(f"/api/v1/projects/{pid}/versions", json={"label": "лишняя"},
                       headers=auth_headers)
    assert over.status_code == 409


def test_versions_isolated_across_tenants(client, register):
    owner = register(email="a@e.ru", org="A")
    other = register(email="b@e.ru", org="B")
    pid = _project(client, owner)
    vid = client.post(f"/api/v1/projects/{pid}/versions", json={"label": "V"},
                      headers=owner).json()["id"]
    # чужой арендатор не видит ни проект, ни версии
    assert client.get(f"/api/v1/projects/{pid}/versions", headers=other).status_code == 404
    assert client.get(f"/api/v1/projects/{pid}/versions/{vid}",
                      headers=other).status_code == 404


def test_version_missing_404(client, auth_headers):
    pid = _project(client, auth_headers)
    assert client.get(f"/api/v1/projects/{pid}/versions/nope",
                      headers=auth_headers).status_code == 404
    assert client.get(f"/api/v1/projects/{pid}/versions/nope/diff",
                      headers=auth_headers).status_code == 404


def test_version_requires_auth(client, auth_headers):
    pid = _project(client, auth_headers)
    assert client.post(f"/api/v1/projects/{pid}/versions", json={"label": "V"}).status_code in (401, 403)
