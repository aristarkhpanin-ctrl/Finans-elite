"""Страховые взносы со сдельной оплаты (0.9.52, пакет J — найдено при ручной сверке кофейни).

Взносы начисляются на любые выплаты по трудовому договору (ст. 420 НК РФ), а движок
грузил ими только оклады штата (I13–I15): сдельная оплата (I6, C3) шла без взносов, и у
производства на сдельщине себестоимость была занижена на треть фонда оплаты. Теперь
загрузка одна — ``pipeline.payroll_load`` — на штат, сдельщину и маржу продуктов.
"""
from __future__ import annotations

from decimal import Decimal

from calc_core import run
from calc_core.engine.pipeline import payroll_load
from calc_core.models import (
    BomLine,
    CostFunction,
    DirectCostKind,
    DirectCostLine,
    Material,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StaffPosition,
)

d = Decimal
N = 6


def _model(rate: str, *, piece_line: bool = True, bom: bool = False) -> ProjectModel:
    products = [Product(id="p", name="Изделие", piece_wage_per_unit=d(10) if bom else d(0),
                        bom=[BomLine(material_id="m", qty_per_unit=d(1))] if bom else [])]
    return ProjectModel(
        header=ProjectHeader(name="Сдельщина", duration_months=N),
        settings=ProjectSettings(payroll_contribution_rate=d(rate), profit_tax_rate=d(0)),
        operating_plan=OperatingPlan(
            materials=[Material(id="m", name="Сырьё", unit_price=d(5))] if bom else [],
            products=products,
            sales=[SalesLine(product_id="p", volume=[d(100)] * N, price=[d(50)] * N)],
            direct_costs=[DirectCostLine(name="Сдельная оплата",
                                         kind=DirectCostKind.PIECE_WAGES,
                                         amount=[d(1000)] * N)] if piece_line else [],
            staff=[StaffPosition(name="Мастер", monthly_salary=d(2000),
                                 function=CostFunction.STAFF_PRODUCTION)],
        ),
    )


def test_piece_wages_carry_the_same_contributions_as_salaries():
    r = run(_model("0.30"))
    # 1000 + 30% взносов; взносы — в следующем месяце (0.9.54), поэтому первый месяц без них
    assert r.cashflow["C3"] == [d(1000)] + [d(1300)] * (N - 1)
    assert r.income["I14"] == [d(2600)] * N               # оклад — с теми же 30%
    assert sum(r.income["I6"], d(0)) == d(1300) * N       # в себестоимости — со взносами


def test_without_a_contribution_rate_nothing_changes():
    r = run(_model("0"))
    assert r.cashflow["C3"] == [d(1000)] * N
    assert payroll_load(_model("0")) == 1


def test_product_margin_counts_the_same_loaded_piece_wage():
    """Маржа продукта считает сдельщину той же загрузкой, что и I6: иначе сумма по
    продуктам разошлась бы с отчётом на треть фонда оплаты."""
    r = run(_model("0.30", piece_line=False, bom=True))
    margins = r.product_margins.products
    assert len(margins) == 1
    assert margins[0].piece_wages == d(100) * d(10) * d("1.3") * N
    assert margins[0].piece_wages == sum(r.income["I6"], d(0))
