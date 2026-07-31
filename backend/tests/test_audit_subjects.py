"""Субъекты анализа (Финанс-Аудит, продукт №2): CRUD, изоляция арендатора, инвариант.

Только слой хранения/API — ядро первого продукта не затрагивается.
"""
from __future__ import annotations


def _model(*, balanced: bool = True):
    """Модель субъекта на 2 периода. balanced=False — актив ≠ пассив во 2-м периоде."""
    return {
        "name": "ООО «Пример»",
        "currency": "RUB",
        "industry": "Торговля",
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["100", "120"],
            "A_INVENTORY": ["30", "35"],
            "A_RECEIVABLE": ["40", "45"],
            "A_CASH": ["30", "50"],          # актив: 200, 250
            "P_EQUITY": ["120", "150" if balanced else "999"],
            "P_LONG": ["30", "30"],
            "P_SHORT": ["50", "70"],         # пассив: 200, 250 (или 250→1099 при !balanced)
        },
        "income": {
            "I_REVENUE": ["500", "600"],
            "I_COGS": ["300", "360"],
            "I_OPEX": ["80", "90"],
            "I_INTEREST": ["10", "12"],
            "I_OTHER": ["0", "0"],
            "I_TAX": ["22", "28"],
        },
    }


def _create(client, headers, **kw):
    return client.post("/api/v1/audit/subjects",
                       json={"name": "ООО «Пример»", "model": _model(**kw)}, headers=headers)


def test_create_get_list_subject(client, auth_headers):
    r = _create(client, auth_headers)
    assert r.status_code == 201
    sub = r.json()
    assert sub["n_periods"] == 2
    assert sub["balanced"] is True
    assert [str(x) for x in sub["balance_gap"]] == ["0", "0"]
    sid = sub["id"]

    got = client.get(f"/api/v1/audit/subjects/{sid}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["model"]["balance"]["A_FIXED"] == ["100", "120"]

    lst = client.get("/api/v1/audit/subjects", headers=auth_headers).json()
    assert len(lst) == 1 and lst[0]["id"] == sid and lst[0]["balanced"] is True


def test_unbalanced_flagged(client, auth_headers):
    sub = _create(client, auth_headers, balanced=False).json()
    assert sub["balanced"] is False
    # актив 2-го периода 250, пассив 250−150+999 = 1099 → разрыв 250−1099 = −849
    assert sub["balance_gap"][0] in ("0", 0)
    assert str(sub["balance_gap"][1]) == "-849"


def test_update_and_delete(client, auth_headers):
    sid = _create(client, auth_headers).json()["id"]
    upd = client.put(f"/api/v1/audit/subjects/{sid}",
                     json={"name": "Переименовано"}, headers=auth_headers)
    assert upd.status_code == 200 and upd.json()["name"] == "Переименовано"

    d = client.delete(f"/api/v1/audit/subjects/{sid}", headers=auth_headers)
    assert d.status_code == 204
    assert client.get(f"/api/v1/audit/subjects/{sid}", headers=auth_headers).status_code == 404


def test_tenant_isolation(client, register):
    a = register(email="a@e.ru", org="Орг A")
    b = register(email="b@e.ru", org="Орг B")
    sid = _create(client, a).json()["id"]
    # чужой субъект невидим и недоступен из другой организации
    assert client.get(f"/api/v1/audit/subjects/{sid}", headers=b).status_code == 404
    assert client.get("/api/v1/audit/subjects", headers=b).json() == []
    assert client.delete(f"/api/v1/audit/subjects/{sid}", headers=b).status_code == 404
    # владельцу — доступен
    assert client.get(f"/api/v1/audit/subjects/{sid}", headers=a).status_code == 200


def test_auth_required(client):
    assert client.get("/api/v1/audit/subjects").status_code in (401, 403)
