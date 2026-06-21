from decimal import Decimal

from calc_core.series import add, cumulative, const, scale, sub, total, zeros


def test_zeros_and_const():
    assert zeros(3) == [Decimal(0)] * 3
    assert const(5, 3) == [Decimal(5)] * 3


def test_add_sub():
    a = [Decimal(1), Decimal(2), Decimal(3)]
    b = [Decimal(10), Decimal(20), Decimal(30)]
    assert add(a, b) == [Decimal(11), Decimal(22), Decimal(33)]
    assert sub(b, a) == [Decimal(9), Decimal(18), Decimal(27)]


def test_scale_and_total():
    a = [Decimal(1), Decimal(2), Decimal(3)]
    assert scale(a, 2) == [Decimal(2), Decimal(4), Decimal(6)]
    assert total(a) == Decimal(6)


def test_cumulative():
    assert cumulative([Decimal(1), Decimal(2), Decimal(3)]) == [Decimal(1), Decimal(3), Decimal(6)]


def test_length_mismatch_raises():
    try:
        add([Decimal(1)], [Decimal(1), Decimal(2)])
    except ValueError:
        return
    raise AssertionError("ожидалась ValueError при разной длине рядов")
