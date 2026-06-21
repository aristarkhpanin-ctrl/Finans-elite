"""Тесты анализа безубыточности (7.2)."""
from decimal import Decimal

from calc_core import run
from calc_core.reports.breakeven import compute_break_even
from calc_core.reports.lines import INCOME_LINES
from calc_core.reports.statements import Statement
from calc_core.samples import build_sample_project


def _income(values: dict) -> Statement:
    s = Statement(INCOME_LINES, 1)
    for k, v in values.items():
        s[k] = [Decimal(v)]
    return s


def test_break_even_known_values():
    # выручка 100, переменные (I7) 40, постоянные (I16) 30
    inc = _income({"I4": 100, "I7": 40, "I8": 60, "I16": 30})
    be = compute_break_even(inc, 1)
    # BE = 30 / (60/100) = 50; запас прочности = (100−50)/100 = 0.5
    assert be.break_even_revenue[0] == Decimal(50)
    assert be.margin_of_safety[0] == Decimal("0.5")


def test_break_even_includes_depreciation_and_interest():
    inc = _income({"I4": 200, "I7": 80, "I8": 120, "I16": 30, "I17": 20, "I18": 10, "I9": 0})
    be = compute_break_even(inc, 1)
    # постоянные = 30+20+10 = 60; CM-ratio = 120/200 = 0.6; BE = 60/0.6 = 100
    assert be.break_even_revenue[0] == Decimal(100)
    assert be.margin_of_safety[0] == Decimal("0.5")


def test_break_even_none_when_no_revenue_or_margin():
    assert compute_break_even(_income({"I4": 0, "I8": 0}), 1).break_even_revenue[0] is None
    # отрицательная маржа → безубыточность не определена
    assert compute_break_even(_income({"I4": 100, "I7": 120, "I8": -20, "I16": 5}), 1).break_even_revenue[0] is None


def test_break_even_on_sample():
    r = run(build_sample_project())
    assert len(r.break_even.break_even_revenue) == r.n
    # в демо валовая прибыль положительна → безубыточность определена
    assert any(v is not None for v in r.break_even.break_even_revenue)
