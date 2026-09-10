"""Отраслевые шаблоны моделей (ADMIN-DECOMPOSITION.md, D4).

Пустая модель — худший экран продукта: человек, впервые открывший планировщик, не знает,
с какой стороны к нему подойти, и уходит. Шаблон отвечает на вопрос «как **такая**
экономика выражается в этой модели»: где у кафе рецептура, где у перевозок лизинг, где у
подписки предоплата.

**Шаблон — скелет, а не отраслевая норма.** Числа в нём выдуманы автором шаблона и годятся
ровно на то, чтобы модель считалась и было видно, куда что подставлять. Базы отраслевых
данных у платформы нет (см. «Отраслевые ориентиры»: там тот же отказ напечатан рядом с
числами), и выдать пример за статистику значило бы соврать самым дорогим способом — цифрой,
похожей на правду. Поэтому у каждого шаблона есть ``assumptions``: что именно придумано и
что обязательно заменить. Список едет в API и на экран — **вместе** с моделью, а не
где-то рядом.

**Шаблон ничего не считает и ничем не управляет.** Это функция, возвращающая
``ProjectModel``; дальше он живёт как обычный проект пользователя. Методики не касается:
`ENGINE_VERSION` не бампится, golden-снимок движка шаблоны не включает — их держит
отдельный тест «каждый шаблон считается и баланс сходится».
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable

from .models import (
    Asset,
    AssetCategory,
    AutoFinancing,
    BomLine,
    Company,
    CostFunction,
    DirectCostKind,
    DirectCostLine,
    EquityInjection,
    Financing,
    FixedCostLine,
    InvestmentPlan,
    Lease,
    Loan,
    Material,
    OperatingPlan,
    PaymentTerms,
    Product,
    ProductionLine,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    RepaymentType,
    SalesLine,
    StaffPosition,
    StartingBalance,
)

d = Decimal
_START = date(2026, 1, 1)

#: Оговорка, общая для всех шаблонов. Стоит первой в списке допущений: остальные
#: уточняют её, а она называет главное — числа здесь ничьи.
NOT_A_BENCHMARK = (
    "Числа в шаблоне — пример, а не отраслевая норма: базы отраслевых данных у платформы "
    "нет. Замените их своими, иначе расчёт покажет чужую экономику."
)


@dataclass(frozen=True)
class Template:
    """Шаблон быстрого старта: модель + честный список допущений."""

    id: str
    name: str
    #: Отрасль человеческим словом — по ней шаблон и ищут.
    industry: str
    description: str
    #: Чем шаблон полезен помимо чисел: какую машинерию модели он показывает.
    shows: str
    #: Что придумано и что обязательно заменить. Первым пунктом — что это не норма.
    assumptions: list[str] = field(default_factory=list)
    build: Callable[[], ProjectModel] | None = None


def _settings(**over) -> ProjectSettings:
    """Общая настройка: ставка дисконтирования, налоги, НДС. Отрасли меняют, что нужно."""
    base = dict(discount_rate_annual=d("0.18"), profit_tax_rate=d("0.20"),
                vat_rate=d("0.20"), payroll_contribution_rate=d("0.30"))
    base.update(over)
    return ProjectSettings(**base)


# --- Кафе: рецептура, сдельная оплата, оборудование ---

def build_cafe() -> ProjectModel:
    """Кофейня: рецептура блюда (BOM), фонд оплаты по штату, оборудование в рассрочку."""
    n = 24
    return ProjectModel(
        header=ProjectHeader(name="Кофейня", start_date=_START, duration_months=n),
        settings=_settings(inflation_sales=d("0.06"), inflation_direct=d("0.08"),
                           inflation_wages=d("0.07")),
        operating_plan=OperatingPlan(
            materials=[
                Material(id="m_coffee", name="Кофе зерновой", unit="кг", unit_price=d(1800),
                         payment_delay_months=1),
                Material(id="m_milk", name="Молоко", unit="л", unit_price=d(80)),
                Material(id="m_cup", name="Стакан с крышкой", unit="шт", unit_price=d(12)),
            ],
            products=[
                Product(id="p_coffee", name="Кофе с молоком",
                        bom=[BomLine(material_id="m_coffee", qty_per_unit=d("0.018")),
                             BomLine(material_id="m_milk", qty_per_unit=d("0.2")),
                             BomLine(material_id="m_cup", qty_per_unit=d(1))],
                        piece_wage_per_unit=d(15)),
                Product(id="p_bake", name="Выпечка (закупка)"),
            ],
            sales=[
                SalesLine(product_id="p_coffee",
                          volume=[d(4200)] * 6 + [d(5200)] * 18, price=[d(230)] * n),
                SalesLine(product_id="p_bake",
                          volume=[d(1300)] * 6 + [d(1600)] * 18, price=[d(160)] * n),
            ],
            direct_costs=[
                DirectCostLine(name="Закупка выпечки", kind=DirectCostKind.MATERIALS,
                               amount=[d(78000)] * 6 + [d(96000)] * 18,
                               payment_delay_months=1),
            ],
            staff=[
                StaffPosition(name="Бариста", monthly_salary=d(55000), headcount=d(3),
                              function=CostFunction.STAFF_PRODUCTION),
                StaffPosition(name="Управляющий", monthly_salary=d(90000),
                              function=CostFunction.STAFF_ADMIN),
            ],
            fixed_costs=[
                FixedCostLine(name="Аренда помещения", function=CostFunction.ADMIN,
                              amount=[d(260000)] * n),
                FixedCostLine(name="Коммунальные и связь", function=CostFunction.ADMIN,
                              amount=[d(35000)] * n),
                FixedCostLine(name="Реклама и лояльность", function=CostFunction.MARKETING,
                              amount=[d(40000)] * n),
                FixedCostLine(name="Уборка, посуда, касса, эквайринг",
                              function=CostFunction.ADMIN, amount=[d(70000)] * n),
            ],
        ),
        investment_plan=InvestmentPlan(assets=[
            Asset(name="Кофемашина и мельница", cost=d(1200000), purchase_month=0,
                  life_months=60, category=AssetCategory.EQUIPMENT),
            Asset(name="Мебель и ремонт", cost=d(1800000), purchase_month=0,
                  life_months=84, category=AssetCategory.EQUIPMENT),
        ]),
        financing=Financing(
            equity=[EquityInjection(amount=d(2500000), month=0)],
            loans=[Loan(name="Кредит на оборудование", amount=d(1200000), start_month=0,
                        term_months=36, annual_rate=d("0.22"),
                        repayment=RepaymentType.EQUAL_PRINCIPAL)],
            common_shares=d(1000),
        ),
    )


# --- Подписка (SaaS): предоплата, штат разработки, почти нет материалов ---

def build_saas() -> ProjectModel:
    """Сервис по подписке: выручка предоплатой, издержки — люди и хостинг."""
    n = 48
    growth = [d(150 + 45 * i) for i in range(n)]           # абонентов в месяц
    return ProjectModel(
        header=ProjectHeader(name="Сервис по подписке", start_date=_START,
                             duration_months=n),
        settings=_settings(discount_rate_annual=d("0.25"), terminal_growth_rate=d("0.05"),
                           valuation_earnings_multiple=d(8), inflation_wages=d("0.08")),
        operating_plan=OperatingPlan(
            products=[Product(id="p_sub", name="Подписка, мес.")],
            sales=[SalesLine(product_id="p_sub", volume=growth, price=[d(2400)] * n,
                             payment=PaymentTerms(prepayment_share=d(1)))],
            direct_costs=[
                DirectCostLine(name="Хостинг и инфраструктура",
                               kind=DirectCostKind.MATERIALS,
                               amount=[d(60) * v for v in growth]),
            ],
            staff=[
                StaffPosition(name="Разработчик", monthly_salary=d(250000), headcount=d(3),
                              function=CostFunction.STAFF_PRODUCTION),
                StaffPosition(name="Поддержка", monthly_salary=d(90000), headcount=d(2),
                              function=CostFunction.STAFF_PRODUCTION),
                StaffPosition(name="Маркетолог", monthly_salary=d(150000),
                              function=CostFunction.STAFF_MARKETING),
            ],
            fixed_costs=[
                FixedCostLine(name="Привлечение клиентов", function=CostFunction.MARKETING,
                              amount=[d(350000)] * n),
                FixedCostLine(name="Офис и сервисы", function=CostFunction.ADMIN,
                              amount=[d(150000)] * n),
            ],
        ),
        investment_plan=InvestmentPlan(assets=[
            Asset(name="Право на платформу (НМА)", cost=d(3000000), purchase_month=0,
                  life_months=60, category=AssetCategory.INTANGIBLE),
            Asset(name="Техника команды", cost=d(900000), purchase_month=0,
                  life_months=36, category=AssetCategory.EQUIPMENT),
        ]),
        financing=Financing(
            equity=[EquityInjection(amount=d(16000000), month=0),
                    EquityInjection(amount=d(9000000), month=10)],
            common_shares=d(10000),
        ),
    )


# --- Перевозки: транспорт в лизинге, топливо в прямых издержках ---

def build_logistics() -> ProjectModel:
    """Грузоперевозки: парк в финансовом лизинге, топливо и ремонт — прямые издержки."""
    n = 36
    trips = [d(36)] * 6 + [d(44)] * (n - 6)
    return ProjectModel(
        header=ProjectHeader(name="Грузоперевозки", start_date=_START, duration_months=n),
        settings=_settings(inflation_direct=d("0.09"), inflation_sales=d("0.07"),
                           property_tax_rate=d("0.022")),
        operating_plan=OperatingPlan(
            products=[Product(id="p_trip", name="Рейс (до 1000 км)")],
            sales=[SalesLine(product_id="p_trip", volume=trips, price=[d(95000)] * n,
                             payment=PaymentTerms(payment_delay_months=1))],
            direct_costs=[
                DirectCostLine(name="Топливо", kind=DirectCostKind.MATERIALS,
                               amount=[d(25000) * t for t in trips]),
                DirectCostLine(name="Ремонт и шины", kind=DirectCostKind.MATERIALS,
                               amount=[d(350000)] * n, payment_delay_months=1),
                DirectCostLine(name="Оплата водителей за рейс",
                               kind=DirectCostKind.PIECE_WAGES,
                               amount=[d(12000) * t for t in trips]),
            ],
            staff=[
                StaffPosition(name="Логист", monthly_salary=d(110000), headcount=d(3),
                              function=CostFunction.STAFF_PRODUCTION),
                StaffPosition(name="Бухгалтер", monthly_salary=d(95000),
                              function=CostFunction.STAFF_ADMIN),
            ],
            fixed_costs=[
                FixedCostLine(name="Стоянка и диспетчерская", function=CostFunction.ADMIN,
                              amount=[d(250000)] * n),
                FixedCostLine(name="Страхование парка", function=CostFunction.ADMIN,
                              amount=[d(180000)] * n),
            ],
        ),
        investment_plan=InvestmentPlan(assets=[
            Asset(name="Тягач (собственный)", cost=d(9000000), purchase_month=0,
                  life_months=84, category=AssetCategory.EQUIPMENT),
        ]),
        financing=Financing(
            equity=[EquityInjection(amount=d(12000000), month=0)],
            leases=[Lease(name="Три тягача в финансовом лизинге",
                          monthly_payment=d(750000), start_month=0, term_months=36,
                          finance=True, annual_rate=d("0.19"))],
            # Входной НДС с покупки тягача возвращается не сразу — разрыв закрывает линия.
            auto_financing=AutoFinancing(enabled=True, annual_rate=d("0.21"),
                                         min_balance=d(300000)),
            common_shares=d(1000),
        ),
    )


# --- Аренда недвижимости: здание, длинная амортизация, ипотечный кредит ---

def build_rental() -> ProjectModel:
    """Доходная недвижимость: покупка здания в кредит и сдача площадей в аренду."""
    n = 120
    return ProjectModel(
        header=ProjectHeader(name="Аренда помещений", start_date=_START,
                             duration_months=n),
        settings=_settings(discount_rate_annual=d("0.14"), terminal_growth_rate=d("0.04"),
                           property_tax_rate=d("0.022"), inflation_sales=d("0.05"),
                           liquidation_recovery_rate=d("0.9")),
        operating_plan=OperatingPlan(
            products=[Product(id="p_m2", name="Аренда, м² в месяц")],
            sales=[SalesLine(product_id="p_m2",
                             volume=[d(0)] * 2 + [d(900)] * 4 + [d(1150)] * (n - 6),
                             price=[d(1900)] * n,
                             payment=PaymentTerms(prepayment_share=d(1)))],
            fixed_costs=[
                FixedCostLine(name="Эксплуатация и уборка", function=CostFunction.ADMIN,
                              amount=[d(320000)] * n),
                FixedCostLine(name="Управляющая компания", function=CostFunction.ADMIN,
                              amount=[d(150000)] * n),
            ],
            staff=[StaffPosition(name="Управляющий объектом", monthly_salary=d(120000),
                                 function=CostFunction.STAFF_ADMIN)],
        ),
        investment_plan=InvestmentPlan(assets=[
            Asset(name="Здание", cost=d(120000000), purchase_month=0, life_months=360,
                  category=AssetCategory.BUILDINGS),
            Asset(name="Земельный участок", cost=d(25000000), purchase_month=0,
                  category=AssetCategory.LAND),
        ]),
        financing=Financing(
            equity=[EquityInjection(amount=d(90000000), month=0)],
            loans=[Loan(name="Кредит под залог объекта", amount=d(60000000),
                        start_month=0, term_months=120, annual_rate=d("0.16"),
                        repayment=RepaymentType.EQUAL_PRINCIPAL)],
            # Входной НДС с покупки объекта возвращается не сразу: до возврата кассовый
            # разрыв закрывает кредитная линия — как это и бывает в жизни.
            auto_financing=AutoFinancing(enabled=True, annual_rate=d("0.19"),
                                         min_balance=d(1000000)),
            common_shares=d(10000),
        ),
    )


# --- Сельское хозяйство: длинный цикл, сезонная выручка ---

def build_farming() -> ProjectModel:
    """Растениеводство: затраты весной, выручка осенью, длинный производственный цикл."""
    n = 36
    season = lambda base, months: [  # noqa: E731 — короткий помощник сезонности
        base if (t % 12) in months else d(0) for t in range(n)]
    return ProjectModel(
        header=ProjectHeader(name="Растениеводство", start_date=_START,
                             duration_months=n),
        settings=_settings(profit_tax_rate=d("0.06"), vat_rate=d("0.10"),
                           production_cycle_months=5, inflation_direct=d("0.10"),
                           property_tax_rate=d(0)),
        operating_plan=OperatingPlan(
            products=[Product(id="p_grain", name="Зерно, т")],
            sales=[SalesLine(product_id="p_grain", volume=season(d(1500), (8, 9, 10)),
                             price=[d(14000)] * n,
                             payment=PaymentTerms(payment_delay_months=1))],
            production=[ProductionLine(product_id="p_grain",
                                       volume=season(d(1500), (3, 4, 5)))],
            direct_costs=[
                DirectCostLine(name="Семена и удобрения", kind=DirectCostKind.MATERIALS,
                               amount=season(d(4500000), (2, 3)), payment_delay_months=1),
                DirectCostLine(name="ГСМ", kind=DirectCostKind.MATERIALS,
                               amount=season(d(2200000), (3, 4, 8, 9))),
            ],
            staff=[
                StaffPosition(name="Механизатор", monthly_salary=d(85000), headcount=d(6),
                              function=CostFunction.STAFF_PRODUCTION),
                StaffPosition(name="Агроном", monthly_salary=d(130000),
                              function=CostFunction.STAFF_PRODUCTION),
            ],
            fixed_costs=[
                FixedCostLine(name="Аренда земли", function=CostFunction.ADMIN,
                              amount=[d(600000)] * n),
                FixedCostLine(name="Хранение и подработка", function=CostFunction.ADMIN,
                              amount=season(d(1500000), (9, 10, 11))),
            ],
        ),
        investment_plan=InvestmentPlan(assets=[
            Asset(name="Трактор с навесным", cost=d(14000000), purchase_month=0,
                  life_months=120, category=AssetCategory.EQUIPMENT),
            Asset(name="Зернохранилище", cost=d(9000000), purchase_month=0,
                  life_months=240, category=AssetCategory.BUILDINGS),
        ]),
        financing=Financing(
            equity=[EquityInjection(amount=d(25000000), month=0)],
            loans=[Loan(name="Сезонный кредит", amount=d(8000000), start_month=2,
                        term_months=12, annual_rate=d("0.12"),
                        repayment=RepaymentType.BULLET)],
            # Посевная и уборочная закрываются кредитной линией: выручка приходит осенью.
            auto_financing=AutoFinancing(enabled=True, annual_rate=d("0.14"),
                                         min_balance=d(500000)),
            common_shares=d(1000),
        ),
    )


# --- Розница: магазин у дома, наценка, инкассация ---

def build_retail() -> ProjectModel:
    """Магазин у дома: закупка с отсрочкой, продажа за наличные, товарный запас."""
    n = 24
    return ProjectModel(
        header=ProjectHeader(name="Магазин у дома", start_date=_START, duration_months=n),
        settings=_settings(inflation_sales=d("0.06"), inflation_direct=d("0.06")),
        company=Company(starting_balance=StartingBalance(
            cash=d(500000), finished_goods=d(1500000), paid_in_capital=d(2000000))),
        operating_plan=OperatingPlan(
            products=[Product(id="p_basket", name="Средний чек")],
            sales=[SalesLine(product_id="p_basket",
                             volume=[d(9000)] * 6 + [d(10500)] * 18, price=[d(750)] * n)],
            direct_costs=[
                DirectCostLine(name="Закупка товара", kind=DirectCostKind.MATERIALS,
                               amount=[d(4860000)] * 6 + [d(5670000)] * 18,
                               payment_delay_months=1, stock_lead_months=1),
            ],
            staff=[
                StaffPosition(name="Продавец-кассир", monthly_salary=d(60000),
                              headcount=d(4), function=CostFunction.STAFF_PRODUCTION),
                StaffPosition(name="Заведующий", monthly_salary=d(100000),
                              function=CostFunction.STAFF_ADMIN),
            ],
            fixed_costs=[
                FixedCostLine(name="Аренда торгового зала", function=CostFunction.ADMIN,
                              amount=[d(350000)] * n),
                FixedCostLine(name="Эквайринг и инкассация", function=CostFunction.ADMIN,
                              amount=[d(120000)] * n),
            ],
        ),
        investment_plan=InvestmentPlan(assets=[
            Asset(name="Торговое оборудование", cost=d(2200000), purchase_month=0,
                  life_months=60, category=AssetCategory.EQUIPMENT),
        ]),
        financing=Financing(
            equity=[EquityInjection(amount=d(2200000), month=0)],
            loans=[Loan(name="Оборотный кредит", amount=d(2000000), start_month=0,
                        term_months=24, annual_rate=d("0.21"),
                        repayment=RepaymentType.EQUAL_PRINCIPAL)],
            common_shares=d(1000),
        ),
    )


#: Отраслевые шаблоны. Ключ стабилен — на него ссылаются интерфейс и ссылки на шаблон.
INDUSTRY_TEMPLATES: dict[str, Template] = {
    t.id: t for t in [
        Template(
            id="cafe", name="Кофейня", industry="Общественное питание",
            description="Точка с рецептурой напитка, штатом и оборудованием в кредит.",
            shows="Рецептура (нормы расхода на порцию), сдельная оплата, штатное "
                  "расписание, оборудование с амортизацией.",
            assumptions=[
                NOT_A_BENCHMARK,
                "Проходимость (4200 напитков в месяц с выходом на 5200) и средний чек "
                "выдуманы: замените их своими замерами или расчётом по локации.",
                "Аренда задана суммой в месяц. В общепите она часто считается процентом "
                "от выручки — это другая строка, и на неё модель среагирует иначе.",
                "Списания и потери продуктов не заложены вовсе: реальная себестоимость "
                "выше рецептурной, и на этом теряется вся видимая прибыль.",
                "Кредит гасится равными долями тела — аннуитета движок пока не умеет. "
                "Для банковского графика платёж в первые месяцы будет выше расчётного.",
            ],
            build=build_cafe),
        Template(
            id="saas", name="Сервис по подписке", industry="ИТ и сервисы",
            description="Подписка с предоплатой, штат разработки, НМА на платформу.",
            shows="Предоплата (деньги раньше выручки), НМА как класс актива, рост "
                  "абонентской базы рядом с расходами на привлечение.",
            assumptions=[
                NOT_A_BENCHMARK,
                "Линейный рост базы на 45 абонентов в месяц — самое смелое допущение "
                "шаблона: реальная воронка так себя не ведёт.",
                "Отток (churn) не заложен: база только растёт. Без оттока подписная "
                "модель красива всегда — задайте его первым делом.",
                "Стоимость привлечения задана суммой, а не ценой за абонента; связь "
                "«потратили — пришли» в модели не выражена.",
                "Горизонт 4 года выбран не случайно: на трёх годах модель ещё не "
                "окупается, и это правда о подписке, а не ошибка расчёта.",
            ],
            build=build_saas),
        Template(
            id="logistics", name="Грузоперевозки", industry="Транспорт и логистика",
            description="Парк в финансовом лизинге, топливо и оплата водителей за рейс.",
            shows="Финансовый лизинг рядом с покупкой в собственность, сдельная оплата, "
                  "отсрочка платежа от заказчиков, кредитная линия под возврат НДС.",
            assumptions=[
                NOT_A_BENCHMARK,
                "Загрузка постоянна (36 рейсов в месяц с выходом на 44): сезонности, "
                "простоев и порожних пробегов в шаблоне нет.",
                "Высокая доходность здесь — свойство схемы, а не отрасли: парк в "
                "лизинге, собственных вложений мало, и IRR считается на них.",
                "Штрафы, платные дороги и весовой контроль не заложены.",
            ],
            build=build_logistics),
        Template(
            id="rental", name="Аренда помещений", industry="Недвижимость",
            description="Покупка объекта в кредит и сдача площадей арендаторам.",
            shows="Длинная амортизация здания, земля без амортизации, возврат входного "
                  "НДС с покупки, кредитная линия на кассовый разрыв.",
            assumptions=[
                NOT_A_BENCHMARK,
                "NPV отрицателен — и это не поломка: за десять лет объект не "
                "«проедается», почти вся его ценность остаётся в самом здании, а NPV "
                "остаточную стоимость не учитывает. Смотрите блок оценки бизнеса.",
                "Заполняемость выходит на 1150 м² к седьмому месяцу и больше не падает; "
                "вакансия и ротация арендаторов не заложены.",
                "Капитальный ремонт за горизонтом десяти лет не предусмотрен — для "
                "здания это существенное упрощение.",
            ],
            build=build_rental),
        Template(
            id="farming", name="Растениеводство", industry="Сельское хозяйство",
            description="Затраты весной, выручка осенью, длинный производственный цикл.",
            shows="Производственный цикл (НЗП), сезонные ряды, льготная ставка налога и "
                  "НДС 10%, сезонный кредит и кредитная линия.",
            assumptions=[
                NOT_A_BENCHMARK,
                "Урожайность и цена реализации постоянны из года в год — в этой отрасли "
                "так не бывает: проверьте сценариями и Монте-Карло.",
                "Погодные потери и страхование урожая не заложены.",
                "Господдержка (субсидии) не учтена — это отдельная строка прочих доходов.",
            ],
            build=build_farming),
        Template(
            id="retail", name="Магазин у дома", industry="Розничная торговля",
            description="Действующая точка: закупка с отсрочкой, продажа за наличные.",
            shows="Товарный запас с опережающей закупкой, стартовый баланс действующего "
                  "бизнеса, оборотный кредит.",
            assumptions=[
                NOT_A_BENCHMARK,
                "IRR у этого шаблона не определена, и это правильно: действующий магазин "
                "живёт на своём обороте, поток начинается с прихода — нормы доходности "
                "«на вложенное» здесь просто нет.",
                "Наценка задана двумя независимыми рядами («объём × цена» и сумма "
                "закупки): следите, чтобы при правке они не разъехались.",
                "Списания, воровство и уценка не заложены.",
                "Сезонность спроса не задана — в рознице она обычно заметна.",
            ],
            build=build_retail),
    ]
}
