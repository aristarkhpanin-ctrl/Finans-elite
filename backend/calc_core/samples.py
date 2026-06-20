"""Демонстрационные проекты для тестов и примеров."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import (
    Asset,
    Company,
    DirectCostLine,
    EquityInjection,
    Financing,
    FixedCostLine,
    InvestmentPlan,
    Loan,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from .models.common import CostFunction, DirectCostKind, RepaymentType


def build_sample_project() -> ProjectModel:
    """Небольшой производственный проект на 12 месяцев (демо).

    Стартуем «с нуля» (пустой стартовый баланс); финансирование — взнос капитала и заём.
    """
    n = 12
    rub = Decimal

    return ProjectModel(
        header=ProjectHeader(
            name="Демо: мини-производство",
            start_date=date(2026, 1, 1),
            duration_months=n,
        ),
        settings=ProjectSettings(
            discount_rate_annual=rub("0.15"),
            profit_tax_rate=rub("0.20"),
            property_tax_rate=rub("0.022"),
        ),
        company=Company(starting_balance=StartingBalance()),  # с нуля
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Изделие А")],
            sales=[
                SalesLine(
                    product_id="p1",
                    volume=[rub(100)] * n,
                    price=[rub("1000")] * n,
                )
            ],
            direct_costs=[
                DirectCostLine(
                    name="Материалы",
                    kind=DirectCostKind.MATERIALS,
                    amount=[rub("40000")] * n,  # 400/ед × 100
                ),
                DirectCostLine(
                    name="Сдельная оплата",
                    kind=DirectCostKind.PIECE_WAGES,
                    amount=[rub("10000")] * n,
                ),
            ],
            fixed_costs=[
                FixedCostLine(
                    name="Аренда и администрация",
                    function=CostFunction.ADMIN,
                    amount=[rub("15000")] * n,
                ),
                FixedCostLine(
                    name="Зарплата производства",
                    function=CostFunction.STAFF_PRODUCTION,
                    amount=[rub("20000")] * n,
                ),
            ],
        ),
        investment_plan=InvestmentPlan(
            assets=[
                Asset(name="Станок", cost=rub("240000"), purchase_month=0, life_months=24),
            ]
        ),
        financing=Financing(
            equity=[EquityInjection(amount=rub("200000"), month=0)],
            loans=[
                Loan(
                    name="Инвесткредит",
                    amount=rub("150000"),
                    start_month=0,
                    term_months=12,
                    annual_rate=rub("0.18"),
                    repayment=RepaymentType.EQUAL_PRINCIPAL,
                )
            ],
            dividends=[rub(0)] * n,
        ),
    )
