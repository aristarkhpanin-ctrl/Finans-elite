"""Момент признания НДС: «по отгрузке» vs «по оплате» (SPEC §11, §22.2).

«По оплате»: НДС с продаж попадает в бюджет по факту получения денег (а не отгрузки),
входной НДС — по факту оплаты поставщику. Разрыв между начислением и признанием
паркуется в балансе: отложенный исходящий НДС → B21, входной НДС вне зачёта → B7.
Балансовый инвариант сохраняется в обоих режимах.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.money import quantize
from calc_core.models import (
    Company,
    CostFunction,
    Financing,
    FixedCostLine,
    OperatingPlan,
    PaymentTerms,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
    VatBasis,
)

D = Decimal


def _balanced(r) -> bool:
    return [quantize(v) for v in r.balance["B20"]] == [quantize(v) for v in r.balance["B34"]]


def _credit_sale_model(basis: VatBasis) -> ProjectModel:
    """2 мес.: отгрузка 1000 ₽ нетто в t0, оплата (с НДS 20%) в t1; налог на прибыль 0."""
    n = 2
    return ProjectModel(
        header=ProjectHeader(name="vat", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(
            discount_rate_annual=D("0"), profit_tax_rate=D("0"),
            property_tax_rate=D("0"), vat_rate=D("0.20"), vat_basis=basis,
        ),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Товар")],
            sales=[SalesLine(
                product_id="p1", volume=[D(10), D(0)], price=[D(100), D(100)],
                payment=PaymentTerms(payment_delay_months=1),  # деньги через месяц
            )],
        ),
        financing=Financing(common_shares=D(100)),
    )


def test_shipment_basis_pays_vat_at_shipment():
    """По отгрузке: НДС 200 в бюджет сразу (t0), деньги уходят раньше выручки."""
    r = run(_credit_sale_model(VatBasis.SHIPMENT))
    assert r.cashflow["C12"] == [D(200), D(0)]      # НДС к уплате в t0
    assert r.balance["B21"] == [D(0), D(0)]         # отложенного НДС нет
    assert r.balance["B1"] == [D(-200), D(1000)]    # касса уходит в минус в t0
    assert _balanced(r)


def test_payment_basis_defers_vat_until_cash():
    """По оплате: НДС 200 в бюджет в t1 (по факту денег); в t0 — отложен в B21."""
    r = run(_credit_sale_model(VatBasis.PAYMENT))
    assert r.cashflow["C12"] == [D(0), D(200)]      # НДС к уплате по получению денег
    assert r.balance["B21"] == [D(200), D(0)]       # отложенный исходящий НДС в t0
    assert r.balance["B1"] == [D(0), D(1000)]       # касса не уходит в минус
    assert _balanced(r)


def test_both_bases_converge_to_same_end_state():
    """Различается только тайминг: на конец горизонта деньги и прибыль совпадают."""
    rs = run(_credit_sale_model(VatBasis.SHIPMENT))
    rp = run(_credit_sale_model(VatBasis.PAYMENT))
    assert rs.balance["B1"][-1] == rp.balance["B1"][-1] == D(1000)
    assert rs.balance["B32"][-1] == rp.balance["B32"][-1]  # прибыль одинакова


def _input_vat_model(basis: VatBasis) -> ProjectModel:
    """Услуга 100 ₽ нетто + НДС в t0, оплата поставщику в t1; без продаж."""
    n = 2
    return ProjectModel(
        header=ProjectHeader(name="vat-in", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(
            discount_rate_annual=D("0"), profit_tax_rate=D("0"),
            property_tax_rate=D("0"), vat_rate=D("0.20"), vat_basis=basis,
        ),
        company=Company(starting_balance=StartingBalance(
            cash=D(1000), paid_in_capital=D(1000),  # стартовый капитал, чтобы не уйти в минус
        )),
        operating_plan=OperatingPlan(
            fixed_costs=[FixedCostLine(
                name="Услуга", function=CostFunction.ADMIN,
                amount=[D(100), D(0)], payment_delay_months=1,
            )],
        ),
        financing=Financing(common_shares=D(100)),
    )


def test_input_vat_held_in_b7_and_balance_holds():
    """Входной НДС 20 учитывается в B7; баланс сходится в обоих режимах."""
    for basis in (VatBasis.SHIPMENT, VatBasis.PAYMENT):
        r = run(_input_vat_model(basis))
        assert r.balance["B7"][0] == D(20)   # входной НДС-актив 20 в t0
        assert _balanced(r)
