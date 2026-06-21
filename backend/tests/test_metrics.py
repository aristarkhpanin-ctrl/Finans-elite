from decimal import Decimal

from calc_core.metrics import (
    annual_to_monthly,
    irr_annual,
    npv,
    payback_months,
)
from calc_core.money import ONE


def test_annual_to_monthly_compounds_back():
    m = annual_to_monthly(Decimal("0.1925"))  # ~1.5%/мес
    assert abs((ONE + m) ** 12 - ONE - Decimal("0.1925")) < Decimal("1e-6")


def test_npv_zero_rate_is_sum():
    flow = [Decimal(-100), Decimal(60), Decimal(60)]
    assert npv(flow, Decimal(0)) == Decimal(20)


def test_irr_simple():
    # -100 сейчас, +110 через месяц => месячная ставка 10% => годовая ~213.8%
    flow = [Decimal(-100), Decimal(110)]
    irr = irr_annual(flow)
    assert irr is not None
    expected = (ONE + Decimal("0.10")) ** 12 - ONE
    assert abs(irr - expected) < Decimal("0.01")


def test_irr_none_when_no_sign_change():
    assert irr_annual([Decimal(10), Decimal(20)]) is None


def test_payback():
    # накопленный поток: -100, -60, -20, +20 → неотрицателен в 4-м периоде (1-индексация)
    assert payback_months([Decimal(-100), Decimal(40), Decimal(40), Decimal(40)]) == 4
    assert payback_months([Decimal(-100), Decimal(10)]) is None
