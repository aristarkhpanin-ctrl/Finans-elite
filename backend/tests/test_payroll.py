"""Страховые взносы с ФОТ: загрузка затрат на персонал (SPEC §8, §11)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    CostFunction,
    FixedCostLine,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
)

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def _staff_model(rate: str, n: int = 1) -> ProjectModel:
    return ProjectModel(
        header=ProjectHeader(name="payroll", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(payroll_contribution_rate=D(rate), profit_tax_rate=D("0"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        operating_plan=OperatingPlan(
            fixed_costs=[FixedCostLine(name="ЗП", function=CostFunction.STAFF_ADMIN,
                                       amount=[D(1000)] * n)],
        ),
    )


def test_payroll_contribution_loads_staff_cost():
    """ЗП 1000 + взносы 30% = 1300 в начислении (I13/I16) и в выплате (C6); баланс сходится."""
    r = run(_staff_model("0.30"))
    assert r.income["I13"] == [D(1300)]
    assert r.income["I16"] == [D(1300)]
    assert r.cashflow["C6"] == [D(1300)]
    assert _balanced(r)


def test_no_contribution_rate_is_unchanged():
    """Ставка 0 → затраты на персонал не загружаются (backward-compatible)."""
    r = run(_staff_model("0"))
    assert r.income["I13"] == [D(1000)]
    assert r.cashflow["C6"] == [D(1000)]


def test_contribution_reduces_taxable_profit():
    """Взносы — вычитаемая издержка: уменьшают налог. Выручка 5000, ЗП 1000 + 30% взносы."""
    m = ProjectModel(
        header=ProjectHeader(duration_months=1),
        settings=ProjectSettings(payroll_contribution_rate=D("0.30"), profit_tax_rate=D("0.20"),
                                 property_tax_rate=D("0"), vat_rate=D("0")),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=[D(50)], price=[D(100)])],
            fixed_costs=[FixedCostLine(name="ЗП", function=CostFunction.STAFF_ADMIN,
                                       amount=[D(1000)])],
        ),
    )
    r = run(m)
    assert r.income["I23"] == [D(3700)]    # 5000 − 1300 (загруженный ФОТ)
    assert r.income["I27"] == [D(740)]     # 20% от 3700 (а не от 4000)
    assert _balanced(r)
