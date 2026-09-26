"""Сравнение дел (Финанс-Аудит, «Экран 20»; методика — SPEC, Приложение С).

Проверяются решения методики, которые легко потерять при следующей правке:

* «кто лучше» выводится только там, где «лучше» определено (С.1);
* победителя нет, когда значение есть не у всех и когда ничья (С.1);
* сводного балла с весами нет — есть счёт побед по видимым строкам (С.2);
* рекомендации по сделке нет (С.3);
* оговорки сопоставимости выводятся, а валюты снимают победителей у денег (С.4);
* дело без отчётности названо, а не выпало молча (С.5).
"""
from __future__ import annotations

from decimal import Decimal

from audit_core.compare import NOT_COMPUTED, compare_subjects
from audit_core.models import AuditSubjectModel

D = Decimal

VALUATION = {
    "enabled": True, "wacc": "0.20", "terminal_growth": "0.03", "tax_rate": "0.20",
    "growth": ["0.08"], "capex": ["70"], "nwc_change": ["20"],
}


def case(name: str, revenue: str = "1980", **over) -> AuditSubjectModel:
    """Дело на 2 года; отличия задаются точечно."""
    data = {
        "name": name, "industry": "Оптовая торговля", "currency": "RUB",
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["400", "440"], "A_INVENTORY": ["300", "330"],
            "A_RECEIVABLE": ["200", "220"], "A_CASH": ["100", "130"],
            "P_EQUITY": ["500", "600"], "P_LONG": ["200", "200"], "P_SHORT": ["300", "320"],
        },
        "income": {
            "I_REVENUE": ["1800", revenue], "I_COGS": ["1260", "1386"],
            "I_OPEX": ["340", "374"], "I_INTEREST": ["40", "40"],
            "I_OTHER": ["0", "0"], "I_TAX": ["32", "36"],
            "M_DEPRECIATION": ["50", "60"],
        },
        "valuation": dict(VALUATION),
    }
    for key, value in over.items():
        if key in ("balance", "income", "valuation"):
            data[key] = {**data[key], **value}       # type: ignore[dict-item]
        else:
            data[key] = value
    return AuditSubjectModel.model_validate(data)


def compare(*models: AuditSubjectModel):
    return compare_subjects([(f"id{i}", m) for i, m in enumerate(models)])


def row(result, key: str):
    found = [r for r in result.rows if r.key == key]
    assert len(found) == 1, f"ожидалась одна строка {key}"
    return found[0]


# ── С.1. Победитель ──────────────────────────────────────────────────────────

def test_winner_is_the_better_value_by_the_declared_direction():
    result = compare(case("Первое", "1980"), case("Второе", "2400"))
    assert row(result, "revenue").direction == "higher"
    assert row(result, "revenue").winner == 1
    assert row(result, "leverage").direction == "lower"


def test_size_metrics_have_no_winner_at_all():
    """Больше — это размер, а не качество сделки: «лучше» здесь не определено."""
    result = compare(case("Первое", "1980"), case("Второе", "2400"))
    for key in ("enterprise_value", "equity_value"):
        item = row(result, key)
        assert item.direction is None and item.winner is None
        assert "размер, а не качество" in item.note


def test_absolute_risk_sum_is_not_compared():
    """Сумма влияния флагов больше у крупного просто потому, что он крупный."""
    result = compare(case("Первое"), case("Второе", "2400"))
    item = row(result, "priced_total")
    assert item.direction is None and item.winner is None
    assert "несопоставима между бизнесами разного размера" in item.note
    # А число тяжёлых флагов сравнимо — направление у него есть.
    assert row(result, "risk_flags").direction == "lower"


def test_missing_value_leaves_no_winner():
    """Сравнивать посчитанное с непосчитанным нельзя."""
    result = compare(case("С оценкой"),
                     case("Без оценки", valuation={"enabled": False}))
    item = row(result, "multiple")
    assert None in item.values
    assert item.winner is None


def test_a_tie_gives_no_winner():
    """«Лучше» требует различия: при равенстве победителя нет."""
    result = compare(case("Первое"), case("Второе"))
    assert row(result, "revenue").winner is None


def test_grade_is_compared_but_declared_a_convention():
    result = compare(case("Первое"), case("Второе"))
    item = row(result, "grade")
    assert item.texts == ["A", "A"]
    assert "объявленное соглашение" in item.note


# ── С.2. Счёт побед вместо балла ─────────────────────────────────────────────

def test_wins_are_counted_per_case_over_comparable_rows():
    result = compare(case("Первое", "1980"), case("Второе", "2400"))
    assert len(result.wins) == 2
    assert sum(result.wins) == result.comparable
    assert result.comparable == sum(1 for r in result.rows if r.winner is not None)


def test_no_weighted_score_is_produced():
    """Балл прячет веса за собой: при тех же числах разные веса дают разный балл."""
    result = compare(case("Первое"), case("Второе"))
    assert not hasattr(result, "score")
    assert not hasattr(result, "weights")
    assert any("Сводный балл с весами" in line for line in result.not_computed)


# ── С.3. Рекомендации нет ────────────────────────────────────────────────────

def test_no_deal_recommendation_is_produced():
    """Платформа, рекомендующая сделку, притворяется инвестором."""
    result = compare(case("Первое"), case("Второе"))
    assert not hasattr(result, "recommendation")
    assert any("Рекомендация по сделке" in line for line in result.not_computed)
    assert len(result.not_computed) == len(NOT_COMPUTED)


# ── С.4. Оговорки сопоставимости ─────────────────────────────────────────────

def test_different_currencies_remove_winners_from_money_rows():
    """Единственная оговорка, которая не только предупреждает, но и запрещает."""
    result = compare(case("Рублёвое"), case("Долларовое", currency="USD"))
    assert row(result, "revenue").direction is None
    assert row(result, "revenue").winner is None
    assert any("Валюты дел различаются" in c for c in result.caveats)
    # Неденежные строки при этом сравниваются по-прежнему.
    assert row(result, "coverage").direction == "higher"


def test_different_industries_are_flagged_for_multiples():
    result = compare(case("Торговля"), case("Подряд", industry="Строительство"))
    assert any("Отрасли различаются" in c for c in result.caveats)


def test_different_reporting_standards_are_flagged():
    result = compare(case("РСБУ"), case("МСФО", reporting_standard="ifrs"))
    assert any("Основы отчётности различаются" in c for c in result.caveats)


def test_different_earnings_measure_breaks_the_multiple():
    """EBIT и EBITDA расходятся на всю амортизацию — кратности несопоставимы."""
    result = compare(case("С амортизацией"),
                     case("Без амортизации", income={"M_DEPRECIATION": []}))
    assert any("Показатели нормализации различаются" in c for c in result.caveats)
    assert row(result, "multiple").winner is None
    assert row(result, "leverage").winner is None


def test_different_last_periods_are_flagged():
    result = compare(case("Первое"),
                     case("Второе", periods=[{"label": "2023", "kind": "year"},
                                             {"label": "2025", "kind": "year"}]))
    assert any("Последние периоды различаются" in c for c in result.caveats)


def test_lower_coverage_is_named_with_the_case():
    """У дела с меньшим охватом риски могут быть выше показанных."""
    result = compare(case("Проверенное", procedure_marks=[
        {"code": "litigation", "status": "done", "note": "картотека чиста"},
        {"code": "tax_debt", "status": "done", "note": "справка ФНС получена"}]),
        case("Непроверенное"))
    caveat = [c for c in result.caveats if "Охват проверки различается" in c]
    assert caveat and "Непроверенное" in caveat[0]


# ── С.5. Дело без отчётности ─────────────────────────────────────────────────

def test_case_without_reporting_is_named_not_silently_dropped():
    result = compare(case("Первое"), case("Второе"),
                     AuditSubjectModel(name="Пустое"))
    assert result.excluded == ["Пустое"]
    assert any("без введённой отчётности" in c for c in result.caveats)
    assert len(result.cases) == 2


def test_fewer_than_two_cases_is_said_rather_than_shown_empty():
    result = compare(case("Одно"))
    assert result.rows == []
    assert any("хотя бы два дела" in c for c in result.caveats)


def test_columns_carry_what_makes_cases_incomparable():
    """Признаки сопоставимости видны в шапке, а не только в оговорках."""
    result = compare(case("Первое"), case("Второе", currency="USD"))
    assert [c.name for c in result.cases] == ["Первое", "Второе"]
    assert [c.currency for c in result.cases] == ["RUB", "USD"]
    assert all(c.last_period == "2024" for c in result.cases)
    assert all(c.verdict for c in result.cases)


# ── API ──────────────────────────────────────────────────────────────────────

def _api_model(name: str, revenue: str = "600", **over) -> dict:
    data = {
        "name": name, "currency": "RUB", "industry": "Торговля",
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["100", "120"], "A_INVENTORY": ["30", "35"],
            "A_RECEIVABLE": ["40", "45"], "A_CASH": ["30", "50"],
            "P_EQUITY": ["120", "150"], "P_LONG": ["30", "30"], "P_SHORT": ["50", "70"],
        },
        "income": {
            "I_REVENUE": ["500", revenue], "I_COGS": ["300", "360"],
            "I_OPEX": ["80", "90"], "I_INTEREST": ["10", "12"],
            "I_OTHER": ["0", "0"], "I_TAX": ["22", "28"],
        },
    }
    data.update(over)
    return data


def _make(client, headers, name: str, **kw) -> str:
    r = client.post("/api/v1/audit/subjects",
                    json={"name": name, "model": _api_model(name, **kw)}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def test_compare_endpoint_returns_columns_rows_and_caveats(client, auth_headers):
    first = _make(client, auth_headers, "Первое")
    second = _make(client, auth_headers, "Второе", revenue="800")
    r = client.post("/api/v1/audit/compare",
                    json={"subject_ids": [first, second]}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert [c["name"] for c in body["cases"]] == ["Первое", "Второе"]
    revenue = [row for row in body["rows"] if row["key"] == "revenue"][0]
    assert revenue["winner"] == 1
    assert sum(body["wins"]) == body["comparable"]
    assert any("Рекомендация по сделке" in line for line in body["not_computed"])


def test_compare_is_isolated_by_organization(client, register):
    """Чужое дело в сравнение не попадает — как и всюду в аудите (404)."""
    mine = register("a@e.ru", "Первая")
    theirs = register("b@e.ru", "Вторая")
    sid = _make(client, theirs, "Чужое")
    r = client.post("/api/v1/audit/compare", json={"subject_ids": [sid]}, headers=mine)
    assert r.status_code == 404


def test_comparison_numbers_equal_the_case_itself():
    """Главный инвариант против третьей копии конвейера.

    Сравнение считает дела не своим порядком слоёв, а общим разбором. Проверяется не
    вызов, а результат: вердикт, охват и оценка в колонке равны тем, что дело
    показывает у себя.
    """
    from audit_core import review_case

    # Сравнение начинается с двух дел; сверяется первая колонка.
    m = case("ООО «Цель»")
    review = review_case(m)
    comparison = compare_subjects([("s1", m), ("s2", case("ООО «Второе»", "2400"))])
    by_key = {r.key: r for r in comparison.rows}
    assert comparison.cases[0].verdict == review.summary.verdict
    assert by_key["coverage"].values[0] == review.procedures.coverage
    assert by_key["risk_flags"].values[0] == Decimal(review.summary.risk_flags)
    assert by_key["equity_value"].values[0] == review.valuation.equity_value
