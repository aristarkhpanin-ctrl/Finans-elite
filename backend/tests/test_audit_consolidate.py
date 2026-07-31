"""Консолидация группы предприятий (Финанс-Аудит, фаза H)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from audit_core import analyze, consolidate_subjects
from audit_core.models import AuditPeriod, AuditSubjectModel
from audit_core.samples import build_quarterly_subject, build_trading_subject

D = Decimal


def _subject(labels: list[str], cash: list[int], equity: list[int]) -> AuditSubjectModel:
    """Простой сходящийся субъект: актив = деньги, пассив = капитал."""
    return AuditSubjectModel(
        periods=[AuditPeriod(label=x, kind="year") for x in labels],
        balance={"A_CASH": [D(v) for v in cash], "P_EQUITY": [D(v) for v in equity]},
        income={"I_REVENUE": [D(100) for _ in labels]},
    )


def _line(result, code):
    for group in (result.balance, result.income):
        for ln in group:
            if ln.code == code:
                return ln.values
    raise AssertionError(code)


def test_sums_matching_periods():
    """Строки складываются по совпадающим периодам; баланс группы сходится."""
    a = _subject(["2023", "2024"], [100, 150], [100, 150])
    b = _subject(["2023", "2024"], [40, 60], [40, 60])
    c = consolidate_subjects([("A", a), ("B", b)])
    assert c.periods_used == ["2023", "2024"]
    r = analyze(c.model)
    assert _line(r, "A_CASH") == [D(140), D(210)]
    assert _line(r, "A_TOTAL") == [D(140), D(210)]
    assert _line(r, "I_REVENUE") == [D(200), D(200)]
    assert r.balanced is True


def test_period_matched_by_label_not_position():
    """Сопоставление по подписи периода, а не по порядковому номеру."""
    a = _subject(["2023", "2024"], [100, 200], [100, 200])
    b = _subject(["2024", "2023"], [10, 1], [10, 1])   # обратный порядок
    c = consolidate_subjects([("A", a), ("B", b)])
    r = analyze(c.model)
    # 2023: 100 + 1; 2024: 200 + 10
    assert _line(r, "A_CASH") == [D(101), D(210)]


def test_only_common_periods_used():
    """Период, которого нет у всех, в свод не входит (иначе сумма занижала бы группу)."""
    a = _subject(["2022", "2023", "2024"], [10, 20, 30], [10, 20, 30])
    b = _subject(["2023", "2024"], [1, 2], [1, 2])
    c = consolidate_subjects([("A", a), ("B", b)])
    assert c.periods_used == ["2023", "2024"]
    assert c.skipped == {"A": ["2022"]}
    assert any("не вошли периоды" in w for w in c.warnings)
    assert _line(analyze(c.model), "A_CASH") == [D(21), D(32)]


def test_no_common_periods():
    """Совсем разные периоды: пустой свод + явное предупреждение."""
    c = consolidate_subjects([("Год", build_trading_subject()),
                              ("Квартал", build_quarterly_subject())])
    assert c.periods_used == []
    assert any("нет ни одного общего отчётного периода" in w for w in c.warnings)
    assert analyze(c.model).n == 0


def test_intragroup_warning_always_present():
    """Оговорка о невычтенных внутригрупповых оборотах присутствует всегда."""
    c = consolidate_subjects([("A", _subject(["2024"], [10], [10]))])
    assert any("внутригрупповые обороты" in w for w in c.warnings)


def test_memo_line_consolidated():
    """Справочная строка (нераспределённая прибыль) тоже складывается — нужна диагностике."""
    a = _subject(["2024"], [100], [100])
    a.balance["M_RETAINED"] = [D(30)]
    b = _subject(["2024"], [50], [50])
    b.balance["M_RETAINED"] = [D(20)]
    c = consolidate_subjects([("A", a), ("B", b)])
    assert c.model.balance["M_RETAINED"] == [D(50)]


def test_empty_members_rejected():
    with pytest.raises(ValueError):
        consolidate_subjects([])


def test_consolidate_endpoint(client, auth_headers):
    """Эндпоинт: свод двух субъектов, состав, оговорки и анализ группы."""
    def make(name: str, cash: str, equity: str) -> str:
        model = {
            "periods": [{"label": "2024", "kind": "year"}],
            "balance": {"A_CASH": [cash], "P_EQUITY": [equity]},
            "income": {"I_REVENUE": ["500"], "I_COGS": ["300"], "I_OPEX": ["100"],
                       "I_INTEREST": ["0"], "I_OTHER": ["0"], "I_TAX": ["20"]},
        }
        return client.post("/api/v1/audit/subjects", json={"name": name, "model": model},
                           headers=auth_headers).json()["id"]

    ids = [make("Мама", "100", "100"), make("Дочка", "40", "40")]
    r = client.post("/api/v1/audit/consolidate",
                    json={"subject_ids": ids, "name": "Наша группа"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["members"] == ["Мама", "Дочка"]
    assert body["periods_used"] == ["2024"]
    assert any("внутригрупповые обороты" in w for w in body["warnings"])
    total = next(ln for ln in body["analysis"]["balance"] if ln["code"] == "A_TOTAL")
    assert str(total["values"][0]) == "140"
    assert body["analysis"]["opinion"]


def test_consolidate_isolated_by_org(client, register):
    """Чужой субъект в свод не попадает (404)."""
    a = register(email="ca@e.ru", org="Орг CA")
    b = register(email="cb@e.ru", org="Орг CB")
    model = {"periods": [{"label": "2024", "kind": "year"}],
             "balance": {"A_CASH": ["10"], "P_EQUITY": ["10"]}, "income": {}}
    sid = client.post("/api/v1/audit/subjects", json={"name": "Чужой", "model": model},
                      headers=a).json()["id"]
    r = client.post("/api/v1/audit/consolidate", json={"subject_ids": [sid]}, headers=b)
    assert r.status_code == 404
