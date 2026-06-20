from decimal import Decimal

from calc_core.money import D, almost_equal, quantize


def test_d_from_float_is_exact():
    # 0.1 как float неточен; через str — точно
    assert D(0.1) == Decimal("0.1")


def test_quantize_half_up():
    assert quantize(Decimal("1.005"), 2) == Decimal("1.01")
    assert quantize(Decimal("2.5"), 0) == Decimal("3")


def test_almost_equal_within_epsilon():
    assert almost_equal(Decimal("100.00"), Decimal("100.009"))
    assert not almost_equal(Decimal("100.00"), Decimal("100.5"))
