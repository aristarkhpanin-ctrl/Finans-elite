"""Сохранённые группы предприятий (Финанс-Аудит, v2): CRUD, свод по составу, изоляция.

Группа хранит **состав**, а не результат: проверяется, что свод пересчитывается по текущей
отчётности участников и что выбывший участник (субъект удалён) назван в оговорках, а не
исчезает молча.
"""
from __future__ import annotations


def _subject(client, headers, name: str, cash: str, revenue: str = "500") -> str:
    model = {
        "periods": [{"label": "2024", "kind": "year"}],
        "balance": {"A_CASH": [cash], "P_EQUITY": [cash]},
        "income": {"I_REVENUE": [revenue], "I_COGS": ["300"], "I_OPEX": ["100"],
                   "I_INTEREST": ["0"], "I_OTHER": ["0"], "I_TAX": ["20"]},
    }
    return client.post("/api/v1/audit/subjects", json={"name": name, "model": model},
                       headers=headers).json()["id"]


def _group(client, headers, ids: list[tuple[str, str]], name: str = "Наша группа",
           elimination: dict | None = None):
    body = {
        "name": name,
        "model": {
            "members": [{"subject_id": sid, "name": nm} for sid, nm in ids],
            "elimination": elimination,
        },
    }
    return client.post("/api/v1/audit/groups", json=body, headers=headers)


def _total_assets(analysis: dict) -> str:
    return str(next(ln for ln in analysis["balance"] if ln["code"] == "A_TOTAL")["values"][0])


def test_create_get_list_group(client, auth_headers):
    """Состав сохраняется и читается; выбывших нет."""
    a = _subject(client, auth_headers, "Мама", "100")
    b = _subject(client, auth_headers, "Дочка", "40")
    r = _group(client, auth_headers, [(a, "Мама"), (b, "Дочка")])
    assert r.status_code == 201
    g = r.json()
    assert g["n_members"] == 2 and g["n_missing"] == 0

    got = client.get(f"/api/v1/audit/groups/{g['id']}", headers=auth_headers).json()
    assert [m["subject_id"] for m in got["model"]["members"]] == [a, b]

    lst = client.get("/api/v1/audit/groups", headers=auth_headers).json()
    assert len(lst) == 1 and lst[0]["name"] == "Наша группа"


def test_group_analyze_sums_members(client, auth_headers):
    """Свод сохранённой группы = сумма участников; имя группы идёт из самой группы."""
    a = _subject(client, auth_headers, "Мама", "100")
    b = _subject(client, auth_headers, "Дочка", "40")
    gid = _group(client, auth_headers, [(a, "Мама"), (b, "Дочка")]).json()["id"]

    r = client.post(f"/api/v1/audit/groups/{gid}/analyze", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["members"] == ["Мама", "Дочка"]
    assert body["missing_members"] == []
    assert body["periods_used"] == ["2024"]
    assert _total_assets(body["analysis"]) == "140"


def test_group_reflects_current_reporting(client, auth_headers):
    """Хранится состав, а не числа: правка отчётности участника меняет свод группы."""
    a = _subject(client, auth_headers, "Мама", "100")
    gid = _group(client, auth_headers, [(a, "Мама")]).json()["id"]
    before = client.post(f"/api/v1/audit/groups/{gid}/analyze", headers=auth_headers).json()
    assert _total_assets(before["analysis"]) == "100"

    model = client.get(f"/api/v1/audit/subjects/{a}", headers=auth_headers).json()["model"]
    model["balance"]["A_CASH"] = ["175"]
    model["balance"]["P_EQUITY"] = ["175"]
    client.put(f"/api/v1/audit/subjects/{a}", json={"model": model}, headers=auth_headers)

    after = client.post(f"/api/v1/audit/groups/{gid}/analyze", headers=auth_headers).json()
    assert _total_assets(after["analysis"]) == "175"


def test_renamed_member_shown_under_new_name(client, auth_headers):
    """У живого участника имя берётся из субъекта — переименование не теряется."""
    a = _subject(client, auth_headers, "Мама", "100")
    gid = _group(client, auth_headers, [(a, "Мама")]).json()["id"]
    client.put(f"/api/v1/audit/subjects/{a}", json={"name": "Мама (новое)"},
               headers=auth_headers)
    body = client.post(f"/api/v1/audit/groups/{gid}/analyze", headers=auth_headers).json()
    assert body["members"] == ["Мама (новое)"]


def test_deleted_member_reported_not_dropped_silently(client, auth_headers):
    """Удалённый участник назван в оговорке: состав изменился — молчать нельзя."""
    a = _subject(client, auth_headers, "Мама", "100")
    b = _subject(client, auth_headers, "Дочка", "40")
    gid = _group(client, auth_headers, [(a, "Мама"), (b, "Дочка")]).json()["id"]
    client.delete(f"/api/v1/audit/subjects/{b}", headers=auth_headers)

    g = client.get(f"/api/v1/audit/groups/{gid}", headers=auth_headers).json()
    assert g["n_members"] == 2 and g["n_missing"] == 1

    body = client.post(f"/api/v1/audit/groups/{gid}/analyze", headers=auth_headers).json()
    assert body["missing_members"] == ["Дочка"]
    assert body["members"] == ["Мама"]
    assert "Дочка" in body["warnings"][0]
    # свод посчитан по оставшемуся участнику
    assert _total_assets(body["analysis"]) == "100"
    # оговорка видна и в предупреждениях самого анализа (их показывает UI)
    assert any("Дочка" in w for w in body["analysis"]["warnings"])


def test_group_without_alive_members_is_empty_not_error(client, auth_headers):
    """Все участники удалены → пустой свод с оговоркой, а не 500."""
    a = _subject(client, auth_headers, "Мама", "100")
    gid = _group(client, auth_headers, [(a, "Мама")]).json()["id"]
    client.delete(f"/api/v1/audit/subjects/{a}", headers=auth_headers)

    r = client.post(f"/api/v1/audit/groups/{gid}/analyze", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["analysis"]["n"] == 0
    assert body["missing_members"] == ["Мама"]
    assert any("не осталось ни одного участника" in w for w in body["warnings"])


def test_group_elimination_applied(client, auth_headers):
    """Сохранённые внутригрупповые обороты применяются при своде группы."""
    a = _subject(client, auth_headers, "Мама", "100", revenue="500")
    b = _subject(client, auth_headers, "Дочка", "40", revenue="300")
    gid = _group(client, auth_headers, [(a, "Мама"), (b, "Дочка")],
                 elimination={"receivables": ["0"], "revenue": ["100"]}).json()["id"]

    body = client.post(f"/api/v1/audit/groups/{gid}/analyze", headers=auth_headers).json()
    revenue = next(ln for ln in body["analysis"]["income"] if ln["code"] == "I_REVENUE")
    assert str(revenue["values"][0]) == "700"          # 500 + 300 − 100
    assert any("исключены заданные внутригрупповые величины" in w for w in body["warnings"])


def test_update_and_delete_group(client, auth_headers):
    """Правка состава и удаление группы; субъекты-участники остаются."""
    a = _subject(client, auth_headers, "Мама", "100")
    b = _subject(client, auth_headers, "Дочка", "40")
    gid = _group(client, auth_headers, [(a, "Мама")]).json()["id"]

    r = client.put(f"/api/v1/audit/groups/{gid}", headers=auth_headers, json={
        "name": "Группа 2",
        "model": {"members": [{"subject_id": a, "name": "Мама"},
                              {"subject_id": b, "name": "Дочка"}], "elimination": None},
    })
    assert r.status_code == 200 and r.json()["n_members"] == 2 and r.json()["name"] == "Группа 2"

    assert client.delete(f"/api/v1/audit/groups/{gid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/audit/groups/{gid}", headers=auth_headers).status_code == 404
    # субъекты не тронуты
    assert client.get(f"/api/v1/audit/subjects/{a}", headers=auth_headers).status_code == 200


def test_group_isolated_by_org(client, register):
    """Чужая группа недоступна (404), чужой субъект в состав не сводится."""
    a = register(email="ga@e.ru", org="Орг GA")
    b = register(email="gb@e.ru", org="Орг GB")
    sid = _subject(client, a, "Свой", "10")
    gid = _group(client, a, [(sid, "Свой")]).json()["id"]

    assert client.get(f"/api/v1/audit/groups/{gid}", headers=b).status_code == 404
    assert client.post(f"/api/v1/audit/groups/{gid}/analyze", headers=b).status_code == 404
    assert client.get("/api/v1/audit/groups", headers=b).json() == []

    # группа чужой организации со ссылкой на «свой» субъект: субъект другой организации
    # не находится → считается выбывшим, а не подмешивается в свод
    gid_b = _group(client, b, [(sid, "Чужой")]).json()["id"]
    body = client.post(f"/api/v1/audit/groups/{gid_b}/analyze", headers=b).json()
    assert body["members"] == [] and body["missing_members"] == ["Чужой"]
