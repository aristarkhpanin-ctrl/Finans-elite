"""MIRR и ARR (SPEC §17): модифицированная IRR и средняя норма рентабельности.

Числа выверены вручную на простых потоках.
"""
from __future__ import annotations

from decimal import Decimal

from calc_core.metrics import annual_to_monthly, arr_annual, irr_annual, mirr_annual
from calc_core.money import quantize as q

D = Decimal
ZERO_RATE = D(0)


def test_mirr_zero_rates_two_periods():
    """Ставки 0: MIRR_м = FV/|PV| − 1 = 120/100 − 1 = 20%/мес → годовая (1.2^12 − 1)."""
    flow = [D(-100), D(120)]
    m = mirr_annual(flow, ZERO_RATE, ZERO_RATE)
    assert m is not None
    assert q(m * 100) == q((D("1.2") ** 12 - 1) * 100)


def test_mirr_equals_irr_for_simple_flow():
    """Для потока с одной сменой знака и ставках = IRR: MIRR = IRR (свойство определения)."""
    flow = [D(-100), D(60), D(60)]
    irr_m_annual = irr_annual(flow)
    assert irr_m_annual is not None
    r_m = annual_to_monthly(irr_m_annual)
    m = mirr_annual(flow, r_m, r_m)
    assert m is not None
    assert abs(m - irr_m_annual) < D("0.0001")


def test_mirr_undefined_without_inflows_or_outflows():
    assert mirr_annual([D(-100), D(-50)], ZERO_RATE, ZERO_RATE) is None
    assert mirr_annual([D(100), D(50)], ZERO_RATE, ZERO_RATE) is None
    assert mirr_annual([D(-100)], ZERO_RATE, ZERO_RATE) is None


def test_arr_average_annual_return_on_investment():
    """Инвестиция 100, поступления 240 за 24 мес (2 года): ARR = (240/2)/100 = 120%."""
    flow = [D(-100)] + [D(10)] * 24
    # investment_graph: дефицит только от первого оттока → потребность 100.
    # 25 мес ≈ 25/12 лет; поступления 240 → ARR = 240/(25/12)/100
    a = arr_annual(flow)
    assert a is not None
    expected = D(240) / (D(25) / D(12)) / D(100)
    assert q(a * 100) == q(expected * 100)


def test_arr_none_without_investment():
    assert arr_annual([D(10), D(10)]) is None
    assert arr_annual([]) is None


def test_metrics_include_mirr_and_arr():
    """MIRR/ARR попадают в метрики результата (демо-проект)."""
    from calc_core import run
    from calc_core.samples import build_sample_project

    m = run(build_sample_project()).metrics
    # демо маргинально (IRR не определена), но ARR считается при наличии инвестиций
    assert m.arr_annual is not None
    # поля существуют и сериализуются
    from calc_core.serialize import metrics_to_dict
    d = metrics_to_dict(m)
    assert "mirr_annual" in d and "arr_annual" in d
