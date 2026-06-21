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
    PaymentTerms,
    Product,
    ProductionLine,
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
                    # 30% предоплата за месяц до поставки, остаток — с отсрочкой 1 мес.
                    payment=PaymentTerms(
                        prepayment_share=rub("0.3"),
                        advance_lead_months=1,
                        payment_delay_months=1,
                    ),
                )
            ],
            # Производство с опережением: 120 ед/мес в 1-м полугодии, 80 — во 2-м
            # (итого 1200 ед = объём сбыта). Образуется запас готовой продукции (B5).
            production=[
                ProductionLine(product_id="p1", volume=[rub(120)] * 6 + [rub(80)] * 6),
            ],
            direct_costs=[
                DirectCostLine(
                    name="Материалы",
                    kind=DirectCostKind.MATERIALS,
                    # 400/ед × объём производства
                    amount=[rub("48000")] * 6 + [rub("32000")] * 6,
                    payment_delay_months=1,  # оплата поставщику с отсрочкой 1 мес.
                    stock_lead_months=1,     # закупка сырья за 1 мес. до потребления → B3
                ),
                DirectCostLine(
                    name="Сдельная оплата",
                    kind=DirectCostKind.PIECE_WAGES,
                    amount=[rub("12000")] * 6 + [rub("8000")] * 6,  # 100/ед × производство
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
