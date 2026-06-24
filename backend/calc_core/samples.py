"""Демонстрационные проекты для тестов и примеров."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import (
    Asset,
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
from .models.common import (
    AssetCategory,
    CostFunction,
    DirectCostKind,
    InventoryMethod,
    RepaymentType,
    VatBasis,
)


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
            common_shares=rub(1000),  # для показателей «на акцию»
        ),
    )


def build_showcase_project() -> ProjectModel:
    """Богатый сбалансированный проект — витрина возможностей ядра (расширяет golden-набор).

    Действующее предприятие с детальным стартовым балансом; одновременно задействованы:
    валютный контур (позиция, экспорт, валютные заём/сырьё/услуга), производственный цикл
    (НЗП), группы ОС (земля/здание/оборудование) с продажей и переоценкой, операционный и
    финансовый лизинг, депозит, налоги (прибыль с льготой, ФОТ-взносы, налог с продаж,
    имущество), НДС «по оплате», ФИФО, инфляция по группам, дивиденды, оценка бизнеса
    (Гордон/DDM/мультипликатор/ликвидация). Фиксирует взаимодействие подмоделей в golden —
    страховка от незаметного «сползания» цифр (CALC-ENGINE-SPEC.md §21.3).
    """
    n = 12
    d = Decimal
    fx_open = d(60)

    return ProjectModel(
        header=ProjectHeader(
            name="Витрина: действующее предприятие",
            start_date=date(2026, 1, 1),
            duration_months=n,
        ),
        settings=ProjectSettings(
            discount_rate_annual=d("0.15"),
            terminal_growth_rate=d("0.03"),
            valuation_earnings_multiple=d("6"),
            liquidation_recovery_rate=d("0.7"),
            profit_tax_rate=d("0.20"),
            profit_tax_benefit_share=d("0.10"),
            payroll_contribution_rate=d("0.30"),
            sales_tax_rate=d("0.01"),
            inflation_sales=d("0.05"),
            inflation_direct=d("0.04"),
            inflation_wages=d("0.06"),
            inflation_general=d("0.03"),
            property_tax_rate=d("0.022"),
            vat_rate=d("0.20"),
            vat_basis=VatBasis.PAYMENT,
            inventory_method=InventoryMethod.FIFO,
            production_cycle_months=2,
        ),
        company=Company(starting_balance=StartingBalance(
            cash=d(100000), fixed_assets_net=d(50000), foreign_monetary=d(1000),
            receivables=d(20000), payables=d(15000), debt=d(30000),
            paid_in_capital=d(185000), retained_earnings=d(0),
        )),
        environment=Environment(fx_open=fx_open, fx_rate=[d(60) + d(i) for i in range(n)]),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Изделие А"), Product(id="p2", name="Экспортный B")],
            sales=[
                SalesLine(product_id="p1", volume=[d(100)] * n, price=[d(1000)] * n,
                          payment=PaymentTerms(prepayment_share=d("0.3"),
                                               advance_lead_months=1, payment_delay_months=1)),
                SalesLine(product_id="p2", volume=[d(20)] * n, price=[d(50)] * n, foreign=True,
                          payment=PaymentTerms(payment_delay_months=2)),
            ],
            production=[
                ProductionLine(product_id="p1", volume=[d(110)] * 6 + [d(90)] * 6),
                ProductionLine(product_id="p2", volume=[d(20)] * n),
            ],
            direct_costs=[
                DirectCostLine(name="Материалы", kind=DirectCostKind.MATERIALS,
                               amount=[d(40000)] * n, payment_delay_months=1, stock_lead_months=1),
                DirectCostLine(name="Импортное сырьё", kind=DirectCostKind.MATERIALS, foreign=True,
                               amount=[d(100)] * n, payment_delay_months=1),
                DirectCostLine(name="Сдельная оплата", kind=DirectCostKind.PIECE_WAGES,
                               amount=[d(12000)] * n),
            ],
            fixed_costs=[
                FixedCostLine(name="Администрация", function=CostFunction.ADMIN, amount=[d(15000)] * n),
                FixedCostLine(name="Зарплата производства", function=CostFunction.STAFF_PRODUCTION,
                              amount=[d(20000)] * n),
                FixedCostLine(name="Представительские", function=CostFunction.MARKETING,
                              amount=[d(3000)] * n, from_profit=True),
                FixedCostLine(name="Валютный консалтинг", function=CostFunction.ADMIN,
                              amount=[d(50)] * n, foreign=True),
            ],
        ),
        investment_plan=InvestmentPlan(assets=[
            Asset(name="Станок", cost=d(240000), purchase_month=0, life_months=24,
                  category=AssetCategory.EQUIPMENT, revaluation_month=6, revaluation_amount=d(20000)),
            Asset(name="Цех", cost=d(360000), purchase_month=0, life_months=120,
                  category=AssetCategory.BUILDINGS),
            Asset(name="Земельный участок", cost=d(150000), purchase_month=0,
                  category=AssetCategory.LAND),
            Asset(name="Автомобиль", cost=d(60000), purchase_month=0, life_months=36,
                  category=AssetCategory.EQUIPMENT, sale_month=9, sale_price=d(40000)),
        ]),
        financing=Financing(
            equity=[EquityInjection(amount=d(200000), month=0)],
            loans=[
                Loan(name="Инвесткредит", amount=d(150000), start_month=0, term_months=12,
                     annual_rate=d("0.18"), repayment=RepaymentType.EQUAL_PRINCIPAL),
                Loan(name="Валютный заём", amount=d(2000), start_month=1, term_months=10,
                     annual_rate=d("0.08"), foreign=True),
                Loan(name="Заём учредителя", amount=d(50000), start_month=0, term_months=12,
                     annual_rate=d("0.12"), repayment=RepaymentType.BULLET, interest_on_profit=True),
            ],
            leases=[
                Lease(name="Оборудование (опер.)", monthly_payment=d(8000),
                      start_month=0, term_months=12),
                Lease(name="Транспорт (фин.)", monthly_payment=d(10000), start_month=0,
                      term_months=12, finance=True, annual_rate=d("0.15")),
            ],
            deposits=[Deposit(name="Депозит", amount=d(80000), start_month=2,
                              term_months=6, annual_rate=d("0.08"))],
            dividends=[d(0)] * 6 + [d(10000)] * 6,
            common_shares=d(1000),
        ),
    )


def build_trade_project() -> ProjectModel:
    """Оптовая торговля (приёмочный сценарий A9): закупка товара и перепродажа с наценкой.

    Без производства (производство = продажам, мгновенно): «материалы» = себестоимость
    закупленного товара (→ COGS при продаже). Действующее предприятие со складским запасом.
    """
    n = 12
    d = Decimal
    return ProjectModel(
        header=ProjectHeader(name="Торговля: опт", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(
            discount_rate_annual=d("0.15"), profit_tax_rate=d("0.20"),
            property_tax_rate=d("0.022"), vat_rate=d("0.20"), vat_basis=VatBasis.SHIPMENT,
            valuation_earnings_multiple=d("5"), liquidation_recovery_rate=d("0.8"),
        ),
        company=Company(starting_balance=StartingBalance(
            cash=d(50000), finished_goods=d(80000), paid_in_capital=d(130000))),
        operating_plan=OperatingPlan(
            products=[Product(id="g1", name="Товар А")],
            sales=[SalesLine(product_id="g1", volume=[d(100)] * n, price=[d(1000)] * n,
                             payment=PaymentTerms(payment_delay_months=1))],
            direct_costs=[
                DirectCostLine(name="Себестоимость товара", kind=DirectCostKind.MATERIALS,
                               amount=[d(60000)] * n, payment_delay_months=1),  # 600/ед закупка
            ],
            fixed_costs=[
                FixedCostLine(name="Аренда склада", function=CostFunction.ADMIN, amount=[d(12000)] * n),
                FixedCostLine(name="Зарплата", function=CostFunction.STAFF_MARKETING,
                              amount=[d(18000)] * n),
            ],
        ),
        financing=Financing(
            loans=[Loan(name="Оборотный кредит", amount=d(100000), start_month=0, term_months=12,
                        annual_rate=d("0.16"), repayment=RepaymentType.EQUAL_PRINCIPAL)],
            dividends=[d(0)] * 6 + [d(8000)] * 6,
            common_shares=d(1000),
        ),
    )


def build_services_project() -> ProjectModel:
    """Услуги (приёмочный сценарий A9): консалтинг без товара/материалов.

    Продажи услуг (выручка без COGS-материалов); издержки — персонал и офис; немного ОС
    (оргтехника). Проверяет режим «продажи с нулевой себестоимостью материалов».
    """
    n = 12
    d = Decimal
    return ProjectModel(
        header=ProjectHeader(name="Услуги: консалтинг", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(
            discount_rate_annual=d("0.15"), profit_tax_rate=d("0.20"),
            property_tax_rate=d("0.022"), vat_rate=d("0.20"), vat_basis=VatBasis.SHIPMENT,
            terminal_growth_rate=d("0.03"), payroll_contribution_rate=d("0.30"),
        ),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="s1", name="Консультация")],
            sales=[SalesLine(product_id="s1", volume=[d(50)] * n, price=[d(2000)] * n,
                             payment=PaymentTerms(prepayment_share=d("0.5"), payment_delay_months=1))],
            fixed_costs=[
                FixedCostLine(name="Зарплата консультантов", function=CostFunction.STAFF_PRODUCTION,
                              amount=[d(50000)] * n),
                FixedCostLine(name="Офис и администрация", function=CostFunction.ADMIN,
                              amount=[d(15000)] * n),
            ],
        ),
        investment_plan=InvestmentPlan(assets=[
            Asset(name="Оргтехника", cost=d(120000), purchase_month=0, life_months=36,
                  category=AssetCategory.EQUIPMENT),
        ]),
        financing=Financing(
            equity=[EquityInjection(amount=d(150000), month=0)],
            dividends=[d(0)] * n, common_shares=d(500),
        ),
    )


# Шаблоны проектов для быстрого старта: id → (название, описание, фабрика модели).
TEMPLATES: dict[str, tuple[str, str, "callable"]] = {
    "production": ("Производство (демо)",
                   "Мини-производство с нуля: выпуск, запасы, заём и капитал.",
                   build_sample_project),
    "trade": ("Торговля (опт)",
              "Закупка товара и перепродажа с наценкой, складской запас, оборотный кредит.",
              build_trade_project),
    "services": ("Услуги (консалтинг)",
                 "Продажа услуг без материалов: персонал, офис, оргтехника, предоплата.",
                 build_services_project),
    "enterprise": ("Действующее предприятие",
                   "Богатый сценарий: стартовый баланс, валюта, лизинг, группы ОС, оценка.",
                   build_showcase_project),
}
