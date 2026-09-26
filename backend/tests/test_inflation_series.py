"""Тесты погодовых рядов инфляции (SPEC §3, gap 1.9, INF0).

Непустой ряд по годам переопределяет скаляр; постоянный ряд ≡ скаляр (тот же индекс);
за пределом ряда держится последнее значение. Пустой ряд → скаляр (golden без дрейфа).
"""
from decimal import Decimal

from calc_core import run
from calc_core.engine.pipeline import _inflation_index, _inflation_year_rates
from calc_core.models import OperatingPlan, Product, ProjectModel, SalesLine
from calc_core.money import almost_equal


def _model(n=24) -> ProjectModel:
    model = ProjectModel()
    model.header.duration_months = n
    model.operating_plan = OperatingPlan(
        products=[Product(id="p1", name="Товар")],
        sales=[SalesLine(product_id="p1", volume=[Decimal(10)] * n, price=[Decimal(1000)] * n)],
    )
    return model


def test_constant_series_equals_scalar_index():
    """Постоянный ряд [r] даёт тот же индекс, что и скаляр r (байт-в-байт)."""
    n = 30
    scalar_idx = _inflation_index(_inflation_year_rates(Decimal("0.10"), []), n)
    series_idx = _inflation_index(_inflation_year_rates(Decimal("0"), [Decimal("0.10")]), n)
    assert scalar_idx == series_idx


def test_series_changes_rate_by_year():
    """Ряд [0, 0.2] — первый год без роста, второй год по 20% годовых."""
    n = 24
    idx = _inflation_index([Decimal("0"), Decimal("0.20")], n)
    assert idx[0] == Decimal(1)
    assert all(v == Decimal(1) for v in idx[:12])           # год 0: без индексации
    assert idx[12] == Decimal(1)                            # начало года 1 — ещё база
    assert idx[13] > Decimal(1)                             # пошёл рост
    # к концу года 1 индекс ≈ 1.20 (годовой рост 20%)
    assert almost_equal(idx[23] * ((Decimal(1) + Decimal("0.20")) ** (Decimal(1) / Decimal(12))),
                        Decimal("1.20"))


def test_series_extends_with_last_value():
    """За пределом ряда держится последнее значение (год 2+ = ставка последнего года)."""
    n = 36
    idx_short = _inflation_index([Decimal("0.10"), Decimal("0.30")], n)     # год 2 = 30%
    idx_full = _inflation_index([Decimal("0.10"), Decimal("0.30"), Decimal("0.30")], n)
    assert idx_short == idx_full


def test_empty_series_uses_scalar_end_to_end():
    """Пустой ряд → скаляр: числа как при скалярной инфляции (обратная совместимость)."""
    scalar = _model()
    scalar.settings.inflation_sales = Decimal("0.15")
    series = _model()
    series.settings.inflation_sales = Decimal("0.15")
    series.settings.inflation_sales_series = []             # пусто → тот же скаляр
    assert run(scalar).income["I1"] == run(series).income["I1"]


def test_series_overrides_scalar_end_to_end():
    """Непустой ряд переопределяет скаляр: выручка растёт по годовым ставкам ряда."""
    m = _model()
    m.settings.inflation_sales = Decimal("0.99")            # скаляр игнорируется
    m.settings.inflation_sales_series = [Decimal("0"), Decimal("0.10")]
    r = run(m)
    # год 0 без инфляции цен → выручка постоянна первые 12 мес.
    assert all(almost_equal(r.income["I1"][t], r.income["I1"][0]) for t in range(12))
    # год 1 растёт → выручка выше базовой
    assert r.income["I1"][23] > r.income["I1"][0]


def test_zero_series_no_indexation():
    assert _inflation_index([Decimal("0"), Decimal("0")], 12) == [Decimal(1)] * 12
    assert _inflation_index([], 5) == [Decimal(1)] * 5


def test_invariant_with_series():
    m = _model()
    m.settings.inflation_sales_series = [Decimal("0.05"), Decimal("0.15")]
    m.settings.inflation_general_series = [Decimal("0.10")]
    r = run(m)
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))
