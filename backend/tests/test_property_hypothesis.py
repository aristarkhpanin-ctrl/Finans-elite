"""Property-тесты движка на Hypothesis (SPEC §16).

В отличие от параметризованного `test_invariants` (50 фикс-сидов), Hypothesis
генерирует модели структурно и при падении *сжимает* контрпример до минимального —
ищет краевые случаи (нулевые ряды, экстремальные ставки, короткие горизонты),
которые ручной генератор пропускает. Главный инвариант — сходимость баланса.

Модель конструируется заведомо валидной (сбалансированный стартовый баланс и валютная
позиция), поэтому `run()` обязан либо посчитать, либо бросить InvariantError — и то, и
другое поймает тест: нарушение тождества B20=B34 = найденный дефект методики.
"""
from __future__ import annotations

from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from calc_core import run
from calc_core.models import (
    Asset,
    AutoFinancing,
    Company,
    Deposit,
    DirectCostLine,
    Environment,
    EquityInjection,
    Financing,
    FixedCostLine,
    InvestmentPlan,
    Lease,
    Loan,
    OperatingPlan,
    PaymentTerms,
    Product,
    ProductionLine,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.models.common import (
    AssetCategory,
    CostFunction,
    DirectCostKind,
    InventoryMethod,
    RepaymentType,
    VatBasis,
)

EPS = Decimal("0.01")


@st.composite
def project_models(draw) -> ProjectModel:
    """Стратегия валидных ProjectModel (целочисленные Decimal — без шума точности)."""
    n = draw(st.integers(min_value=1, max_value=18))

    def ints(lo: int, hi: int) -> int:
        return draw(st.integers(min_value=lo, max_value=hi))

    def series(lo: int, hi: int) -> list[Decimal]:
        return [Decimal(draw(st.integers(min_value=lo, max_value=hi))) for _ in range(n)]

    def share(hi: int = 100) -> Decimal:
        return Decimal(draw(st.integers(min_value=0, max_value=hi))) / Decimal(100)

    def terms() -> PaymentTerms:
        return PaymentTerms(
            prepayment_share=share(),
            advance_lead_months=ints(0, 3),
            payment_delay_months=ints(0, 4),
        )

    n_products = ints(1, 3)
    sales = [
        SalesLine(product_id=f"p{i}", volume=series(0, 200), price=series(10, 500),
                  payment=terms(), foreign=draw(st.booleans()))
        for i in range(n_products)
    ]
    production = [
        ProductionLine(product_id=f"p{i}", volume=series(0, 200))
        for i in range(n_products) if draw(st.booleans())
    ]
    direct = [
        DirectCostLine(name="m", kind=DirectCostKind.MATERIALS, amount=series(0, 30000),
                       payment_delay_months=ints(0, 4), stock_lead_months=ints(0, 3),
                       foreign=draw(st.booleans())),
        DirectCostLine(name="w", kind=DirectCostKind.PIECE_WAGES, amount=series(0, 10000),
                       payment_delay_months=ints(0, 2)),
    ]
    fixed = [
        FixedCostLine(name=f"f{i}", function=draw(st.sampled_from(list(CostFunction))),
                      amount=series(0, 20000), payment_delay_months=ints(0, 3),
                      from_profit=draw(st.booleans()), foreign=draw(st.booleans()))
        for i in range(ints(0, 3))
    ]
    assets = []
    for i in range(ints(0, 3)):
        pm = ints(0, n - 1)
        sell = draw(st.booleans())
        reval = draw(st.booleans())
        assets.append(Asset(
            name=f"a{i}", cost=Decimal(ints(10000, 500000)), purchase_month=pm,
            life_months=ints(1, 36), category=draw(st.sampled_from(list(AssetCategory))),
            sale_month=(ints(pm, n - 1) if sell else None),
            sale_price=(Decimal(ints(0, 500000)) if sell else Decimal(0)),
            revaluation_month=(ints(pm, n - 1) if reval else None),
            revaluation_amount=(Decimal(ints(-50000, 100000)) if reval else Decimal(0)),
        ))
    loans = [
        Loan(name=f"l{i}", amount=Decimal(ints(10000, 300000)), start_month=ints(0, n - 1),
             term_months=ints(1, 24), annual_rate=share(30),
             repayment=draw(st.sampled_from(list(RepaymentType))),
             interest_on_profit=draw(st.booleans()), foreign=draw(st.booleans()))
        for i in range(ints(0, 2))
    ]
    equity = [
        EquityInjection(amount=Decimal(ints(10000, 500000)), month=ints(0, n - 1))
        for _ in range(ints(0, 2))
    ]
    leases = [
        Lease(name=f"ls{i}", monthly_payment=Decimal(ints(0, 20000)), start_month=ints(0, n - 1),
              term_months=ints(1, 24), finance=draw(st.booleans()), annual_rate=share(30))
        for i in range(ints(0, 2))
    ]
    deposits = [
        Deposit(name=f"dp{i}", amount=Decimal(ints(0, 200000)), start_month=ints(0, n - 1),
                term_months=ints(1, 24), annual_rate=share(20))
        for i in range(ints(0, 2))
    ]

    fx_open = Decimal(ints(40, 80))
    fm = Decimal(ints(0, 1000))
    rec, pay = Decimal(ints(0, 5000)), Decimal(ints(0, 5000))
    raw, fg = Decimal(ints(0, 5000)), Decimal(ints(0, 5000))
    # Стартовый баланс уравновешен: активы (валютные + оборотные) = капитал + прибыль.
    company = Company(starting_balance=StartingBalance(
        foreign_monetary=fm, paid_in_capital=fm * fx_open + raw + fg,
        receivables=rec, payables=pay, raw_materials=raw, finished_goods=fg,
        retained_earnings=rec - pay))

    return ProjectModel(
        header=ProjectHeader(duration_months=n),
        company=company,
        environment=Environment(fx_open=fx_open, fx_rate=series(30, 100)),
        settings=ProjectSettings(
            discount_rate_annual=Decimal("0.15"),
            profit_tax_rate=share(30), profit_tax_benefit_share=share(50),
            payroll_contribution_rate=share(40), sales_tax_rate=share(5),
            inflation_sales=share(20), inflation_direct=share(20), inflation_wages=share(20),
            inflation_general=share(20), property_tax_rate=share(3),
            vat_rate=draw(st.sampled_from([Decimal(0), Decimal("0.10"), Decimal("0.20")])),
            vat_basis=draw(st.sampled_from(list(VatBasis))),
            inventory_method=draw(st.sampled_from(list(InventoryMethod))),
            production_cycle_months=ints(0, 3),
        ),
        operating_plan=OperatingPlan(
            products=[Product(id=s.product_id, name=s.product_id) for s in sales],
            sales=sales, production=production, direct_costs=direct, fixed_costs=fixed,
        ),
        investment_plan=InvestmentPlan(assets=assets),
        financing=Financing(loans=loans, leases=leases, deposits=deposits, equity=equity,
                            dividends=series(0, 5000), auto_financing=AutoFinancing(
                                enabled=draw(st.booleans()), annual_rate=share(30),
                                min_balance=Decimal(ints(0, 5000)))),
    )


@given(model=project_models())
@settings(max_examples=200, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
def test_balance_invariant_holds(model: ProjectModel) -> None:
    """Во всех периодах: B20=B34 (актив=пассив), B1=C29 (касса), B32=P7 (прибыль)."""
    result = run(model)
    for t in range(result.n):
        assert abs(result.balance["B20"][t] - result.balance["B34"][t]) <= EPS
        assert abs(result.balance["B1"][t] - result.cashflow["C29"][t]) <= EPS
        assert abs(result.balance["B32"][t] - result.profit_use["P7"][t]) <= EPS
