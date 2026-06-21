"""Инфляция: индексация цен и издержек по группам (SPEC §3)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.engine.pipeline import _inflation_index
from calc_core.money import quantize
from calc_core.models import (
    CostFunction,
    DirectCostLine,
    FixedCostLine,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
)
from calc_core.models.common import DirectCostKind

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def test_inflation_index_base_one_and_compounds_to_annual():
    idx = _inflation_index(D("0.12"), 13)
    assert idx[0] == D(1)                              # период 0 — база
    assert abs(idx[12] - D("1.12")) < D("1e-9")        # 12 месяцев → годовая ставка
    assert _inflation_index(D("0"), 3) == [D(1), D(1), D(1)]  # ноль → без индексации


def _sales_model(infl: str, n: int = 12) -> ProjectModel:
    return ProjectModel(
        header=ProjectHeader(name="infl", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D("0"), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0"),
                                 inflation_sales=D(infl)),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Товар")],
            sales=[SalesLine(product_id="p1", volume=[D(10)] * n, price=[D(100)] * n)],
        ),
    )


def test_sales_inflation_grows_revenue_by_index():
    """Выручка периода = базовая × индекс инфляции; период 0 — без индексации."""
    n = 12
    r = run(_sales_model("0.12", n))
    idx = _inflation_index(D("0.12"), n)
    assert r.income["I1"][0] == D(1000)               # база 10×100
    for t in range(n):
        assert abs(r.income["I1"][t] - D(1000) * idx[t]) < D("0.01")
    assert _balanced(r)


def test_no_inflation_keeps_revenue_flat():
    r = run(_sales_model("0"))
    assert all(v == D(1000) for v in r.income["I1"])


def test_cost_inflation_indexes_direct_and_general():
    """Прямые и общие издержки индексируются своими группами; баланс сходится."""
    n = 6
    m = ProjectModel(
        header=ProjectHeader(duration_months=n),
        settings=ProjectSettings(profit_tax_rate=D("0"), vat_rate=D("0"),
                                 inflation_direct=D("0.12"), inflation_general=D("0.24")),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Товар")],
            sales=[SalesLine(product_id="p1", volume=[D(10)] * n, price=[D(100)] * n)],
            direct_costs=[DirectCostLine(name="мат", kind=DirectCostKind.MATERIALS,
                                         amount=[D(200)] * n)],
            fixed_costs=[FixedCostLine(name="адм", function=CostFunction.ADMIN,
                                       amount=[D(50)] * n)],
        ),
    )
    r = run(m)
    idx_d = _inflation_index(D("0.12"), n)
    idx_g = _inflation_index(D("0.24"), n)
    # I5 (материалы в себестоимости) и I10 (административные) растут по своим индексам
    assert abs(r.income["I10"][n - 1] - D(50) * idx_g[n - 1]) < D("0.01")
    assert abs(r.income["I5"][n - 1] - D(200) * idx_d[n - 1]) < D("0.01")
    assert _balanced(r)
