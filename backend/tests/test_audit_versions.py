"""Версии дела (Финанс-Аудит): снимки модели проверки и анализ изменений.

Проверка идёт итерациями — пришли документы, реестр обязательств поменялся, вердикт
уехал. Без версий на вопрос «что изменилось с прошлой недели» и «какая версия ушла в
комитет» ответить нечем: заключение датировано, но воспроизвести его невозможно.

Проверяются решения, которые легко потерять при следующей правке: сводка снимка
**хранится** (версия — слепок прошлого, а не пересчёт по сегодняшней отчётности),
пустое дело не получает вердикта «ok», диф показывает заголовочные величины дела, а
не 16 коэффициентов, и всё это изолировано по организации.
"""
from __future__ import annotations


def _model(*, revenue: str = "600", equity: str = "150") -> dict:
    """Дело на 2 периода; отличия задаются точечно для дифа."""
    return {
        "name": "ООО «Цель»", "currency": "RUB", "industry": "Торговля",
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["100", "120"], "A_INVENTORY": ["30", "35"],
            "A_RECEIVABLE": ["40", "45"], "A_CASH": ["30", "50"],
            "P_EQUITY": ["120", equity], "P_LONG": ["30", "30"], "P_SHORT": ["50", "70"],
        },
        "income": {
            "I_REVENUE": ["500", revenue], "I_COGS": ["300", "360"], "I_OPEX": ["80", "90"],
            "I_INTEREST": ["10", "12"], "I_OTHER": ["0", "0"], "I_TAX": ["22", "28"],
        },
    }


def _create(client, headers, model: dict | None = None) -> str:
    r = client.post("/api/v1/audit/subjects",
                    json={"name": "ООО «Цель»", "model": model or _model()}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _snap(client, headers, sid: str, label: str = "Перед комитетом"):
    return client.post(f"/api/v1/audit/subjects/{sid}/versions",
                       json={"label": label}, headers=headers)


def test_snapshot_keeps_the_summary_of_its_moment(client, auth_headers):
    """Сводка снимка хранится, а не пересчитывается: версия описывает прошлое."""
    sid = _create(client, auth_headers)
    r = _snap(client, auth_headers, sid)
    assert r.status_code == 201
    saved = r.json()
    assert saved["label"] == "Перед комитетом"
    assert saved["verdict"]                      # дело с отчётностью — вердикт есть

    # Дело правится: выручка выросла вдвое.
    client.put(f"/api/v1/audit/subjects/{sid}",
               json={"name": "ООО «Цель»", "model": _model(revenue="1200")},
               headers=auth_headers)
    listed = client.get(f"/api/v1/audit/subjects/{sid}/versions", headers=auth_headers).json()
    assert listed[0]["verdict"] == saved["verdict"], "снимок пересчитался по новой модели"


def test_empty_case_snapshot_has_no_verdict(client, auth_headers):
    """«ok» у пустого дела читался бы как «проверено, всё хорошо»."""
    sid = _create(client, auth_headers, {"name": "Пустое", "periods": [],
                                         "balance": {}, "income": {}})
    body = _snap(client, auth_headers, sid).json()
    assert body["verdict"] is None and body["risk_flags"] is None


def test_diff_shows_case_headline_values_not_ratios(client, auth_headers):
    """Диф отвечает на вопрос «что стало с делом», а не сыплет коэффициентами."""
    sid = _create(client, auth_headers)
    vid = _snap(client, auth_headers, sid).json()["id"]
    client.put(f"/api/v1/audit/subjects/{sid}",
               json={"name": "ООО «Цель»", "model": _model(revenue="1200")},
               headers=auth_headers)

    diff = client.get(f"/api/v1/audit/subjects/{sid}/versions/{vid}/diff",
                      headers=auth_headers).json()
    assert diff["against"] == "current"
    keys = [m["key"] for m in diff["metric_changes"]]
    assert keys == ["verdict", "risk_flags", "warning_flags", "priced_total",
                    "coverage", "equity_value"]
    # Правка модели видна построчно, путями листьев.
    paths = [c["path"] for c in diff["model_changes"]]
    assert "income.I_REVENUE[1]" in paths
    assert not diff["model_changes_truncated"]


def test_diff_against_another_version(client, auth_headers):
    sid = _create(client, auth_headers)
    first = _snap(client, auth_headers, sid, "Первая").json()["id"]
    client.put(f"/api/v1/audit/subjects/{sid}",
               json={"name": "ООО «Цель»", "model": _model(equity="900")},
               headers=auth_headers)
    second = _snap(client, auth_headers, sid, "Вторая").json()["id"]

    diff = client.get(f"/api/v1/audit/subjects/{sid}/versions/{first}/diff",
                      params={"against": second}, headers=auth_headers).json()
    assert diff["base_id"] == first and diff["against"] == second
    assert any(c["path"] == "balance.P_EQUITY[1]" for c in diff["model_changes"])


def test_restore_returns_the_model_of_the_snapshot(client, auth_headers):
    sid = _create(client, auth_headers)
    vid = _snap(client, auth_headers, sid).json()["id"]
    client.put(f"/api/v1/audit/subjects/{sid}",
               json={"name": "ООО «Цель»", "model": _model(revenue="1200")},
               headers=auth_headers)

    r = client.post(f"/api/v1/audit/subjects/{sid}/versions/{vid}/restore",
                    headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["model"]["income"]["I_REVENUE"][1] == "600"


def test_version_with_full_model_and_deletion(client, auth_headers):
    sid = _create(client, auth_headers)
    vid = _snap(client, auth_headers, sid).json()["id"]
    full = client.get(f"/api/v1/audit/subjects/{sid}/versions/{vid}", headers=auth_headers)
    assert full.status_code == 200 and full.json()["model"]["periods"]

    assert client.delete(f"/api/v1/audit/subjects/{sid}/versions/{vid}",
                         headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/audit/subjects/{sid}/versions",
                      headers=auth_headers).json() == []


def test_versions_are_isolated_by_organization(client, register):
    a = register(email="ver-a@e.ru", org="Орг A")
    b = register(email="ver-b@e.ru", org="Орг B")
    sid = _create(client, a)
    vid = _snap(client, a, sid).json()["id"]

    assert client.get(f"/api/v1/audit/subjects/{sid}/versions", headers=b).status_code == 404
    assert client.get(f"/api/v1/audit/subjects/{sid}/versions/{vid}",
                      headers=b).status_code == 404
    assert client.post(f"/api/v1/audit/subjects/{sid}/versions/{vid}/restore",
                       headers=b).status_code == 404


def test_version_limit_is_named_not_silent(client, auth_headers, monkeypatch):
    """Упереться в предел молча — значит потерять снимок без объяснения."""
    from app import crud
    monkeypatch.setattr(crud, "MAX_VERSIONS_PER_SUBJECT", 1)
    sid = _create(client, auth_headers)
    assert _snap(client, auth_headers, sid, "Одна").status_code == 201
    r = _snap(client, auth_headers, sid, "Вторая")
    assert r.status_code == 409 and "лимит версий" in r.json()["detail"]


def test_snapshot_reaches_the_audit_log(client, auth_headers):
    """Версия — точка, на которую сошлются при разборе: в журнале она обязана быть."""
    sid = _create(client, auth_headers)
    _snap(client, auth_headers, sid, "Для банка")
    org = client.get("/api/v1/organizations", headers=auth_headers).json()[0]["id"]
    entries = client.get(f"/api/v1/organizations/{org}/audit-log",
                         headers=auth_headers).json()["entries"]
    assert any(e["action"] == "case.version" and e["details"] == "Для банка"
               for e in entries)
