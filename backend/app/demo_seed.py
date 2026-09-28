"""Демо-организация: учётные записи и данные для проверки продукта (пакет J, J2).

Проверяющему нужны не пустые экраны, а правдоподобная компания: производство со
сметой запуска и фактом первых месяцев, холдинг, дела «Финанс-Аудита» с отчётностью,
реестром обязательств и оценкой, обсуждение между двумя сотрудниками. Выдумывать всё
это самому — день работы, и проверять потом приходится собственные опечатки.

**Через приложение, а не в таблицы.** Каждое действие — тот же маршрут, по которому ходит
человек (регистрация, приглашение, активация, проекты, дела, версии, обсуждения):
иначе демо-данные обходили бы то, что проверяющий и должен увидеть, — квоты, права,
журнал, проверку баланса. Исключение одно и названо: признак сотрудника платформы
ставится записью в базу, как и ``scripts/set_staff.py`` (маршрута, повышающего права,
у платформы нет намеренно).

**Числа правдоподобные, но выдуманные.** Порядок цен и ставок — рынка 2026 года (ЛЛДПЭ,
стрейч-плёнка, аренда цеха, ставка кредита), но это не отраслевая норма и не чья-то
отчётность: название организации и первый раздел бизнес-плана говорят это прямо.
Реквизиты дел (ИНН, ОГРН) проходят контрольную цифру и не принадлежат ни одной
известной компании; адреса — `.test` (RFC 2606), письма на них не доставляются.

**Самопроверка.** После заведения каждый проект считается тем же маршрутом, что и на
экране, и баланс сверяется помесячно (B20 = B34); отчёт скрипта — таблица показателей.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Protocol

from sqlalchemy.orm import Session

from calc_core.models import (
    Actualization,
    Asset,
    AssetCategory,
    AutoFinancing,
    BomLine,
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
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    RepaymentType,
    SalesLine,
    StaffPosition,
)
from calc_core.models.calendar import CalendarPlan, Resource, Stage, StageResource
from calc_core.models.company import Company, Division
from calc_core.models.project import PlanSection
from calc_core.models.tables import UserRow, UserTable

from . import crud
from .db_models import STAFF_OPERATOR
from .password_policy import check_password
from .security import hash_password

d = Decimal

#: Название организации **само говорит**, что данные вымышлены: организацию видят и в
#: списках, и в служебном контуре, и в выгрузке — оговорка в одном только документе
#: потерялась бы при первом же скриншоте.
DEMO_ORG_NAME = "ООО «Демо Групп» (вымышленные данные)"


@dataclass(frozen=True)
class DemoAccount:
    """Учётная запись демо-организации и её пароль по умолчанию (вне продакшена)."""

    email: str
    full_name: str
    password: str
    role: str


OWNER = DemoAccount("demo@finans-demo.test", "Демо Владелец", "Kvartal-Balans-2026", "owner")
ANALYST = DemoAccount("analyst@finans-demo.test", "Анна Аналитикова", "Analitik-Plan-2026",
                      "analyst")
#: Сотрудник платформы — не участник организации: он видит её снаружи, как оператор.
OPERATOR = DemoAccount("operator@finans-demo.test", "Оператор Платформы",
                       "Kontrol-Servis-2026", "operator")


class SeedError(RuntimeError):
    """Шаг заведения не прошёл: маршрут, ответ и его причина — в сообщении."""


def make_operator(db: Session, password: str) -> str:
    """Сотрудник платформы — записью в базу, как ``scripts/set_staff.py``: маршрута,
    повышающего права, у платформы нет намеренно. Политика пароля — та же, что на
    регистрации: мимо маршрута не значит мимо правил. Возвращает пароль для входа."""
    problem = check_password(password, email=OPERATOR.email)
    if problem:
        raise SeedError(f"Пароль сотрудника платформы: {problem}")
    user = crud.get_user_by_email(db, OPERATOR.email)
    if user is None:
        user = crud.create_user(db, OPERATOR.email, OPERATOR.full_name,
                                hash_password(password))
    crud.set_staff(db, user, is_staff=True, role=STAFF_OPERATOR)
    return password


class _Client(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


class _Api:
    """Тонкая обёртка над клиентом приложения: токен, организация, внятная ошибка."""

    def __init__(self, client: _Client, token: str | None = None,
                 org_id: str | None = None) -> None:
        self.client, self.token, self.org_id = client, token, org_id

    def as_(self, token: str) -> "_Api":
        return _Api(self.client, token, self.org_id)

    def call(self, method: str, path: str, body: Any = None,
             expect: tuple[int, ...] = (200, 201, 204)) -> Any:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.org_id:
            headers["X-Organization-Id"] = self.org_id
        kwargs: dict[str, Any] = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        resp = self.client.request(method, "/api/v1" + path, **kwargs)
        if resp.status_code not in expect:
            raise SeedError(f"{method} {path} → {resp.status_code}: {resp.text[:400]}")
        return resp.json() if resp.content else None


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json")


# --- Флагман «Элиты»: производство стрейч-плёнки -----------------------------------

FLAGSHIP_NAME = "Производство стрейч-плёнки"
#: 60 месяцев — срок инвестиционного кредита: линия со сроком службы 10 лет на трёх
#: годах не окупается, и горизонт короче кредита показал бы NPV вложения, которого не было.
FLAGSHIP_MONTHS = 60
#: Машинная плёнка, кг/мес: пусконаладка, выход на 120 т, затем 150 и 170 т.
MACHINE_VOLUME = [d(0), d(40000), d(80000)] + [d(120000)] * 9 + [d(150000)] * 12 \
    + [d(170000)] * 36
#: Ручные рулоны — со второго полугодия, после отладки перемотки.
HAND_VOLUME = [d(0)] * 6 + [d(15000)] * 6 + [d(25000)] * 48


def build_flagship() -> ProjectModel:
    """Производство стрейч-плёнки: рецептура, штат, линия в кредит, смета запуска."""
    n = FLAGSHIP_MONTHS
    total_volume = [a + b for a, b in zip(MACHINE_VOLUME, HAND_VOLUME, strict=True)]
    return ProjectModel(
        header=ProjectHeader(name=FLAGSHIP_NAME, start_date=date(2026, 1, 1),
                             duration_months=n),
        settings=ProjectSettings(
            discount_rate_annual=d("0.22"), terminal_growth_rate=d("0.04"),
            profit_tax_rate=d("0.25"), vat_rate=d("0.22"), property_tax_rate=d("0.022"),
            payroll_contribution_rate=d("0.30"),
            inflation_sales=d("0.05"), inflation_direct=d("0.06"),
            inflation_wages=d("0.08"), inflation_general=d("0.06"),
            profit_tax_periodicity="quarter", vat_periodicity="quarter"),
        company=Company(divisions=[Division(id="dv_ind", name="Промышленная упаковка"),
                                   Division(id="dv_ret", name="Розничные рулоны")]),
        operating_plan=OperatingPlan(
            materials=[
                Material(id="m_lldpe", name="Полиэтилен ЛЛДПЭ", unit="кг",
                         unit_price=d(126), payment_delay_months=1, stock_lead_months=1),
                Material(id="m_core", name="Втулка картонная", unit="шт", unit_price=d(18)),
                Material(id="m_pack", name="Упаковка и паллеты", unit="кг",
                         unit_price=d("3.5")),
            ],
            products=[
                Product(id="p_machine", name="Стрейч-плёнка машинная, кг",
                        division_id="dv_ind", piece_wage_per_unit=d(4),
                        bom=[BomLine(material_id="m_lldpe", qty_per_unit=d("1.03")),
                             BomLine(material_id="m_core", qty_per_unit=d("0.06")),
                             BomLine(material_id="m_pack", qty_per_unit=d(1))]),
                Product(id="p_hand", name="Стрейч-плёнка ручная, кг",
                        division_id="dv_ret", piece_wage_per_unit=d(7),
                        bom=[BomLine(material_id="m_lldpe", qty_per_unit=d("1.03")),
                             BomLine(material_id="m_core", qty_per_unit=d("0.4")),
                             BomLine(material_id="m_pack", qty_per_unit=d("1.6"))]),
            ],
            sales=[
                SalesLine(product_id="p_machine", volume=MACHINE_VOLUME,
                          price=[d(205)] * n,
                          payment=PaymentTerms(payment_delay_months=1)),
                # Розничные сети платят частично вперёд — видно НДС с авансов (G11).
                SalesLine(product_id="p_hand", volume=HAND_VOLUME, price=[d(230)] * n,
                          payment=PaymentTerms(prepayment_share=d("0.3"),
                                               payment_delay_months=1)),
            ],
            direct_costs=[
                DirectCostLine(name="Электроэнергия линии", kind=DirectCostKind.MATERIALS,
                               amount=[v * d("5.6") for v in total_volume]),
                DirectCostLine(name="Доставка клиентам", kind=DirectCostKind.MATERIALS,
                               amount=[v * d(5) for v in total_volume],
                               payment_delay_months=1),
            ],
            staff=[
                StaffPosition(name="Операторы линии", monthly_salary=d(75000),
                              headcount=d(8), function=CostFunction.STAFF_PRODUCTION),
                StaffPosition(name="Наладчики", monthly_salary=d(95000), headcount=d(2),
                              function=CostFunction.STAFF_PRODUCTION),
                StaffPosition(name="Кладовщики и грузчики", monthly_salary=d(55000),
                              headcount=d(3), function=CostFunction.STAFF_PRODUCTION),
                StaffPosition(name="Технолог", monthly_salary=d(120000),
                              function=CostFunction.STAFF_PRODUCTION),
                StaffPosition(name="Генеральный директор", monthly_salary=d(250000),
                              function=CostFunction.STAFF_ADMIN),
                StaffPosition(name="Главный бухгалтер", monthly_salary=d(120000),
                              function=CostFunction.STAFF_ADMIN),
                StaffPosition(name="Менеджеры по продажам", monthly_salary=d(90000),
                              headcount=d(3), function=CostFunction.STAFF_MARKETING),
            ],
            fixed_costs=[
                FixedCostLine(name="Аренда цеха и склада (2 400 м²)",
                              function=CostFunction.ADMIN, amount=[d(1_080_000)] * n),
                FixedCostLine(name="Коммунальные услуги", function=CostFunction.ADMIN,
                              amount=[d(180_000)] * n),
                FixedCostLine(name="Ремонт и запчасти оборудования",
                              function=CostFunction.PRODUCTION, amount=[d(250_000)] * n),
                FixedCostLine(name="Маркетинг и выставки", function=CostFunction.MARKETING,
                              amount=[d(150_000)] * n),
                FixedCostLine(name="Офис, связь, ПО", function=CostFunction.ADMIN,
                              amount=[d(120_000)] * n),
                FixedCostLine(name="Страхование имущества", function=CostFunction.ADMIN,
                              amount=[d(60_000)] * n),
            ],
        ),
        investment_plan=InvestmentPlan(
            assets=[
                Asset(name="Линия каст-экструзии, 5 слоёв", cost=d(78_000_000),
                      purchase_month=0, life_months=120, category=AssetCategory.EQUIPMENT),
                Asset(name="Перемотчики и чиллер", cost=d(14_000_000), purchase_month=0,
                      life_months=84, category=AssetCategory.EQUIPMENT),
                Asset(name="Подготовка цеха и электрика", cost=d(9_000_000),
                      purchase_month=0, life_months=120, category=AssetCategory.EQUIPMENT),
            ],
            calendar=_launch_calendar(),
        ),
        financing=Financing(
            equity=[EquityInjection(amount=d(60_000_000), month=0)],
            loans=[Loan(name="Инвестиционный кредит", amount=d(70_000_000), start_month=0,
                        term_months=60, annual_rate=d("0.19"),
                        repayment=RepaymentType.ANNUITY)],
            leases=[Lease(name="Погрузчик (операционный лизинг)",
                          monthly_payment=d(95_000), start_month=0, term_months=36)],
            # Разрыв первых месяцев (входной НДС с линии, запасы полимера) закрывает линия.
            auto_financing=AutoFinancing(enabled=True, annual_rate=d("0.21"),
                                         min_balance=d(2_000_000)),
            common_shares=d(10_000),
        ),
        user_tables=[UserTable(id="t_unit", name="Удельные показатели", rows=[
            UserRow(name="Валовая маржа, %", formula="I8 / I4 * 100"),
            UserRow(name="Рентабельность по чистой прибыли, %", formula="I28 / I4 * 100"),
            UserRow(name="EBITDA, ₽", formula="I23 + I18 + I17"),
            UserRow(name="Покрытие процентов EBITDA, раз", formula="(I23 + I18 + I17) / I18"),
        ])],
        business_plan=[
            PlanSection(title="Оговорка", text=(
                "Проект и все числа в нём вымышлены для проверки продукта. Порядок цен и "
                "ставок близок к рынку 2026 года, но это не отраслевая норма и не чья-то "
                "отчётность.")),
            PlanSection(title="Резюме проекта", text=(
                "Запуск производства стрейч-плёнки на линии каст-экструзии в арендованном "
                "цехе: машинная плёнка для промышленной упаковки (выход на 170 т в месяц к "
                "третьему году) и ручные рулоны для розничных сетей. Вложения — 101 млн ₽ "
                "в оборудование и 5,4 млн ₽ в запуск; источники — 60 млн ₽ собственных "
                "средств и инвестиционный кредит 70 млн ₽ под 19% на 5 лет.")),
            PlanSection(title="Сбыт", text=(
                "Машинная плёнка — дистрибьюторам и складам ответственного хранения с "
                "отсрочкой 30 дней. Ручные рулоны — розничным сетям: 30% предоплатой, "
                "остаток через месяц. Цены — без НДС, индексация 5% в год.")),
            PlanSection(title="Производство и сырьё", text=(
                "Основное сырьё — ЛЛДПЭ (1,03 кг на кг плёнки с учётом отходов), закупка "
                "за месяц до производства с отсрочкой оплаты месяц. Сдельная оплата — 4 ₽/кг "
                "машинной и 7 ₽/кг ручной плёнки.")),
            PlanSection(title="Риски", text=(
                "Цена полимера (половина выручки уходит на сырьё), загрузка линии, "
                "дебиторская задолженность дистрибьюторов. Чувствительность NPV к цене "
                "сырья и объёму — на вкладке «Чувствительность» анализа.")),
        ],
    )


def _launch_calendar() -> CalendarPlan:
    """Смета запуска: подготовка цеха → монтаж линии, обучение параллельно."""
    return CalendarPlan(
        resources=[
            Resource(id="r_chief", name="Шеф-монтаж поставщика, чел.-день",
                     unit_price=d(38_000), payment_delay_months=1),
            Resource(id="r_crane", name="Кран и такелаж, смена", unit_price=d(95_000)),
        ],
        stages=[
            Stage(id="s_launch", name="Запуск производства"),
            Stage(id="s_prep", name="Проектирование и подготовка цеха", parent_id="s_launch",
                  start_month=0, duration_months=1, cost=d(1_800_000), amortize_months=12,
                  actual_start_month=0, actual_finish_month=1, actual_cost=d(2_050_000)),
            Stage(id="s_mount", name="Монтаж и пусконаладка линии", parent_id="s_launch",
                  predecessor_id="s_prep", start_month=0, duration_months=1,
                  resources=[StageResource(resource_id="r_chief", quantity=d(60)),
                             StageResource(resource_id="r_crane", quantity=d(8))],
                  actual_start_month=2, actual_finish_month=2, actual_cost=d(3_190_000)),
            Stage(id="s_train", name="Обучение операторов", parent_id="s_launch",
                  start_month=1, duration_months=1, cost=d(600_000),
                  actual_start_month=1, actual_finish_month=1, actual_cost=d(550_000)),
        ],
    )


#: Факт первых восьми месяцев (январь–август 2026) к плану: выручка отстаёт на
#: пусконаладке, полимер дороже плана — обычная картина запуска.
FACT_MONTHS = 8
_RECEIPTS_FACTOR = [d(1), d("0.92"), d("0.95"), d("0.97"), d("1.02"), d("0.98"),
                    d("1.01"), d("0.99")]
_MATERIALS_FACTOR = [d(1), d("1.06"), d("1.04"), d("1.03"), d("1.01"), d("1.02"),
                     d(1), d("1.03")]


def flagship_actuals(cashflow: dict[str, list[Decimal]]) -> Actualization:
    """Факт по плановым строкам кэш-фло: поступления и оплата материалов, округлённо."""
    def fact(code: str, factors: list[Decimal]) -> list[Decimal]:
        return [(cashflow[code][t] * factors[t]).quantize(d(1000))
                for t in range(FACT_MONTHS)]
    return Actualization(actual_until=FACT_MONTHS - 1,
                         actuals={"C1": fact("C1", _RECEIPTS_FACTOR),
                                  "C2": fact("C2", _MATERIALS_FACTOR)})


def stressed(model: ProjectModel, price_factor: Decimal) -> ProjectModel:
    """Та же модель с ценами сбыта × ``price_factor`` — для версии «стресс»."""
    out = model.model_copy(deep=True)
    for line in out.operating_plan.sales:
        line.price = [p * price_factor for p in line.price]
    return out


LOGISTICS_NAME = "Грузоперевозки (дочерняя)"
RETAIL_NAME = "Розничный магазин (действующий, дочерний)"

#: Проекты из отраслевых шаблонов: (id шаблона, имя проекта, горизонт или ``None``).
#: Дочерние холдинга продлены до горизонта головной: свод требует одинаковой
#: длительности, а короткий ряд движок дополнил бы нулями — продажи обнулились бы молча.
TEMPLATE_PROJECTS: list[tuple[str, str, int | None]] = [
    ("cafe", "Кофейня у бизнес-центра", None),
    ("logistics", LOGISTICS_NAME, FLAGSHIP_MONTHS),
    ("retail", RETAIL_NAME, FLAGSHIP_MONTHS),
    ("saas", "Сервис по подписке", None),
]


def prolong(model: dict[str, Any], months: int) -> dict[str, Any]:
    """Продлить модель шаблона до ``months``: каждый помесячный ряд — повтором своего
    последнего месяца («дальше так же»), а не нулями.

    Помесячный ряд узнаётся по длине, равной прежнему горизонту. Лизинг, чей срок
    совпадал с горизонтом, продлевается вместе с ним: иначе парк исчезал бы, а рейсы
    продолжались.
    """
    old = model["header"]["duration_months"]

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            if len(node) == old and node and all(not isinstance(x, (dict, list))
                                                 for x in node):
                return node + [node[-1]] * (months - old)
            return [walk(x) for x in node]
        return node

    out = walk(model)
    out["header"]["duration_months"] = months
    for lease in out["financing"].get("leases", []):
        if lease["start_month"] + lease["term_months"] == old:
            lease["term_months"] = months - lease["start_month"]
    return out


# --- «Финанс-Аудит»: две фирмы-цели -------------------------------------------------

def _years() -> list[dict[str, str]]:
    return [{"label": y, "kind": "year"} for y in ("2023", "2024", "2025")]


def _series(*values: int) -> list[str]:
    return [str(v) for v in values]


def build_translogistic() -> dict[str, Any]:
    """Перевозчик, тыс. ₽: растущий, с долгом и лизингом, оценка и план продавца."""
    return {
        "name": "ООО «ТрансЛогистик»", "currency": "RUB",
        "industry": "Транспорт и логистика", "reporting_standard": "rsbu",
        "periods": _years(),
        "balance": {
            "A_FIXED": _series(210_000, 245_000, 268_000),
            "A_INVENTORY": _series(12_000, 14_500, 15_800),
            "A_RECEIVABLE": _series(58_000, 66_000, 74_500),
            "A_CASH": _series(18_000, 21_500, 27_700),
            "P_EQUITY": _series(120_000, 146_000, 176_000),
            "P_LONG": _series(110_000, 125_000, 118_000),
            "P_SHORT": _series(68_000, 76_000, 92_000),
            "M_RETAINED": _series(105_000, 131_000, 161_000),
        },
        "income": {
            "I_REVENUE": _series(412_000, 468_000, 531_000),
            "I_COGS": _series(318_000, 358_000, 404_000),
            "I_OPEX": _series(44_000, 49_500, 55_000),
            "I_INTEREST": _series(14_200, 16_800, 17_500),
            "I_OTHER": _series(1_200, -800, 2_400),
            # 2023–2024 — по 20%, 2025 — по 25% (п. 1 ст. 284 НК РФ).
            "I_TAX": _series(7_400, 8_580, 14_225),
            "M_DEPRECIATION": _series(26_000, 30_500, 34_000),
        },
        # Реестр — процентный долг (он и уходит в мост EV → цена): 96 000 + 58 000 = 154 000.
        # С балансом (P_LONG + P_SHORT = 210 000) он расходится на 56 000 — это кредиторка
        # поставщикам, и сверка показывает разницу, как и должна: реестр не место для
        # оборотного капитала, иначе цена доли занизилась бы на всю кредиторку.
        "obligations": [
            {"creditor": "ПАО Сбербанк", "contract": "КД-7712/23 от 14.03.2023",
             "kind": "credit", "amount": "96000", "rate": "0.17", "maturity_year": 2029,
             "collateral": "тягачи, 14 ед.", "pledged_amount": "120000",
             "covenant": "Долг / EBITDA ≤ 3,0", "covenant_status": "ok",
             "covenant_note": "проверка ежеквартально по РСБУ"},
            {"creditor": "ВТБ Лизинг", "contract": "ДЛ-4471 от 02.08.2024",
             "kind": "lease", "amount": "58000", "rate": "0.21", "maturity_year": 2028,
             "collateral": "предмет лизинга", "pledged_amount": "58000"},
            {"creditor": "ООО «ТЛ-Склад» (связанная сторона)",
             "contract": "Договор поручительства П-3 от 10.01.2025",
             "kind": "guarantee", "amount": "20000",
             "covenant_note": "поручительство по кредиту связанной стороны"},
        ],
        "earnings_adjustments": [
            {"label": "Вознаграждение собственника выше рыночного", "kind": "owner",
             "amounts": _series(3_600, 3_600, 3_600)},
            {"label": "Доход от продажи списанного тягача (разовый)", "kind": "one_off",
             "amounts": _series(0, 0, -2_400)},
        ],
        "revaluations": [
            {"code": "A_RECEIVABLE", "label": "Безнадёжная дебиторка перевозчика-банкрота",
             "amounts": _series(0, 0, -3_500)},
        ],
        "thresholds": [
            {"ratio": "Коэффициент текущей ликвидности", "direction": "higher",
             "risk_edge": "1.0", "good_edge": "1.3"},
            # Перевозчик с парком в лизинге живёт с плечом выше единицы; универсальный
            # норматив «обязательства ≤ капитала» красил бы его в риск по отрасли.
            {"ratio": "Суммарные обязательства к собств. капиталу", "direction": "lower",
             "risk_edge": "2.0", "good_edge": "1.2"},
        ],
        "user_metrics": [
            {"name": "Выручка на рубль основных средств", "formula": "I_REVENUE / A_FIXED"},
        ],
        "seller_plan": {"I_REVENUE": _series(400_000, 490_000, 580_000)},
        "valuation": {
            "enabled": True, "horizon_years": 5, "wacc": "0.21", "terminal_growth": "0.04",
            "tax_rate": "0.25", "growth": ["0.10", "0.08", "0.07", "0.06", "0.05"],
            "capex": _series(38_000, 40_000, 42_000, 44_000, 46_000),
            "nwc_change": _series(6_000, 5_000, 5_000, 4_000, 4_000),
            "asking_price": "290000",
        },
        "risk": {"iterations": 2000, "seed": 42, "uncertain": [
            {"param": "wacc", "distribution": {"kind": "triangular", "low": "0.18",
                                               "mode": "0.21", "high": "0.25"}},
            {"param": "growth", "distribution": {"kind": "uniform", "low": "0.8",
                                                 "high": "1.2"}},
        ]},
        "report": {
            "number": "DD-2026/014", "date": "2026-09-15",
            "addressee": "Инвестиционный комитет ООО «Демо Групп»",
            "subject_full_name": "Общество с ограниченной ответственностью «ТрансЛогистик»",
            "subject_inn": "7705123452", "subject_ogrn": "1127746123450",
            "subject_address": "г. Москва, ул. Складочная, д. 1 (вымышленный адрес)",
            "executor_name": ANALYST.full_name, "executor_role": "Финансовый аналитик",
            "approver_name": OWNER.full_name, "approver_role": "Генеральный директор",
        },
    }


def build_agro_south() -> dict[str, Any]:
    """Агрохолдинг в долговой яме, тыс. ₽: убытки, проедание капитала, нарушенный ковенант."""
    return {
        "name": "ООО «Агро-Юг»", "currency": "RUB",
        "industry": "Сельское хозяйство", "reporting_standard": "rsbu",
        "periods": _years(),
        "balance": {
            "A_FIXED": _series(150_000, 148_000, 142_000),
            "A_INVENTORY": _series(60_000, 72_000, 81_000),
            "A_RECEIVABLE": _series(25_000, 31_000, 38_000),
            "A_CASH": _series(6_000, 3_000, 1_500),
            "P_EQUITY": _series(60_000, 38_000, 4_000),
            "P_LONG": _series(90_000, 80_000, 60_000),
            "P_SHORT": _series(91_000, 136_000, 198_500),
            "M_RETAINED": _series(40_000, 18_000, -16_000),
        },
        "income": {
            "I_REVENUE": _series(180_000, 162_000, 150_000),
            "I_COGS": _series(158_000, 152_000, 145_000),
            "I_OPEX": _series(18_000, 19_000, 21_000),
            "I_INTEREST": _series(12_000, 14_500, 17_000),
            "I_OTHER": _series(-1_000, 1_500, -1_000),
            "I_TAX": _series(0, 0, 0),
            "M_DEPRECIATION": _series(9_000, 9_500, 9_800),
        },
        # Реестр — процентный долг 130 000; остальные 128 500 пассива — кредиторка
        # поставщикам, её показывает сверка с балансом.
        "obligations": [
            {"creditor": "АО Россельхозбанк", "contract": "КД-118/21 от 20.05.2021",
             "kind": "credit", "amount": "60000", "rate": "0.15", "maturity_year": 2028,
             "collateral": "земли сельхозназначения, техника", "pledged_amount": "95000",
             "covenant": "Долг / EBITDA ≤ 4,0", "covenant_status": "breached",
             "covenant_note": "нарушен по итогам 2025 г.; банк вправе требовать досрочно"},
            {"creditor": "АО Россельхозбанк", "contract": "ВКЛ-204/24 от 11.02.2024",
             "kind": "credit", "amount": "70000", "rate": "0.18", "maturity_year": 2026,
             "collateral": "урожай 2026 г.", "pledged_amount": "70000"},
        ],
        "report": {
            "number": "DD-2026/015", "date": "2026-09-20",
            "subject_full_name": "Общество с ограниченной ответственностью «Агро-Юг»",
            "subject_inn": "2310123454", "subject_ogrn": "1022301123459",
            "executor_name": ANALYST.full_name, "executor_role": "Финансовый аналитик",
        },
    }


AUDIT_CASES: list[tuple[str, Callable[[], dict[str, Any]]]] = [
    ("ООО «ТрансЛогистик» — покупка 100%", build_translogistic),
    ("ООО «Агро-Юг» — кредитный риск", build_agro_south),
]

BENCHMARKS = [
    {"industry": "Транспорт и логистика", "metric": "ev_ebitda", "value": "4.0",
     "source": "Внутренний ориентир ООО «Демо Групп» по сделкам 2024–2025 гг. (вымышлен)"},
    {"industry": "Транспорт и логистика", "metric": "ev_revenue", "value": "0.6",
     "source": "Внутренний ориентир ООО «Демо Групп» (вымышлен)"},
]

CHECKLISTS = [
    {"name": "Покупка перевозчика", "scope": "Транспорт и логистика", "items": [
        "Сверить парк по ПТС и лизинговым договорам с реестром основных средств",
        "Запросить расшифровку дебиторки старше 90 дней",
        "Проверить ковенанты кредитных договоров за последние 4 квартала",
        "Получить справку об отсутствии задолженности по налогам",
    ]},
]


# --- Заведение ---------------------------------------------------------------------

@dataclass
class ProjectCheck:
    """Самопроверка проекта после заведения: считается ли и сходится ли баланс."""

    name: str
    months: int
    npv: Decimal
    irr_annual: Decimal | None
    pb_months: int | None
    revenue_first_year: Decimal
    max_balance_gap: Decimal
    warnings: list[str] = field(default_factory=list)


@dataclass
class CaseCheck:
    """Сводка дела после заведения — тем же разбором, что и экран «Вердикт»."""

    name: str
    verdict: str
    headline: str
    risk_flags: int
    warning_flags: int
    equity_value: Decimal | None
    asking_price: Decimal | None


@dataclass
class SeedReport:
    org_id: str
    org_name: str
    accounts: list[DemoAccount]
    projects: list[ProjectCheck]
    cases: list[CaseCheck]
    notes: list[str]


def _line(statement: dict[str, Any], code: str) -> list[Decimal]:
    for line in statement["lines"]:
        if line["code"] == code:
            return [Decimal(str(v)) for v in line["values"]]
    raise SeedError(f"в ответе расчёта нет строки {code}")


def _money(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _check_project(api: _Api, project_id: str, name: str) -> ProjectCheck:
    """Посчитать проект тем же маршрутом, что и экран, и сверить баланс помесячно."""
    res = api.call("POST", f"/projects/{project_id}/calculate")
    bal = res["balance"]
    gap = max(abs(a - b) for a, b in zip(_line(bal, "B20"), _line(bal, "B34"), strict=True))
    m = res["metrics"]
    return ProjectCheck(
        name=name, months=res["n"], npv=Decimal(str(m["npv"])),
        irr_annual=Decimal(str(m["irr_annual"])) if m["irr_annual"] is not None else None,
        pb_months=m["pb_months"], revenue_first_year=sum(_line(res["income"], "I1")[:12],
                                                         Decimal(0)),
        max_balance_gap=gap, warnings=list(res.get("warnings") or []))


def seed(client: _Client, *, passwords: dict[str, str] | None = None,
         operator: Callable[[], str] | None = None) -> SeedReport:
    """Завести демо-организацию через маршруты приложения.

    ``passwords`` — пароли по адресам (по умолчанию — известные пароли вне продакшена).
    ``operator`` — функция, которая заводит сотрудника платформы в базе и возвращает
    его пароль; ``None`` — оператора нет, тариф остаётся бесплатным (в его квоты данные
    укладываются: пять проектов, три дела, два участника).
    """
    pw = {a.email: a.password for a in (OWNER, ANALYST, OPERATOR)}
    pw.update(passwords or {})
    anon = _Api(client)
    notes: list[str] = []

    # 1. Владелец регистрируется — организация создаётся вместе с ним (как на экране).
    token = anon.call("POST", "/auth/register", {
        "email": OWNER.email, "password": pw[OWNER.email], "full_name": OWNER.full_name,
        "organization_name": DEMO_ORG_NAME})["access_token"]
    owner = _Api(client, token)
    org_id = next(o["id"] for o in owner.call("GET", "/organizations")
                  if o["name"] == DEMO_ORG_NAME)
    owner.org_id = org_id

    # 2. Аналитик — приглашением и активацией, тем же путём, что человек по ссылке.
    invite = owner.call("POST", f"/organizations/{org_id}/members", {
        "email": ANALYST.email, "full_name": ANALYST.full_name, "role": ANALYST.role})
    analyst_token = anon.call("POST", "/auth/activate", {
        "token": invite["invite_token"], "password": pw[ANALYST.email],
        "full_name": ANALYST.full_name})["access_token"]
    analyst = _Api(client, analyst_token, org_id)

    # 3. Оператор платформы (если заведён) назначает тарифы — как по оплаченному счёту.
    accounts = [OWNER, ANALYST]
    if operator is not None:
        op_password = operator()
        op_token = anon.call("POST", "/auth/login", {
            "email": OPERATOR.email, "password": op_password})["access_token"]
        op = _Api(client, op_token)
        for plan in ("team", "audit_team"):
            op.call("POST", f"/admin/organizations/{org_id}/subscription", {
                "plan_code": plan, "months": 12,
                "note": "Демо-данные: счёт не выставлялся"})
        accounts.append(OPERATOR)
    else:
        notes.append("Оператор платформы не заведён: тарифы бесплатные, их квот хватает.")

    # 4. Проекты «Элиты»: флагман (с планом, стрессом и фактом) и отраслевые шаблоны.
    base = build_flagship()
    flagship = owner.call("POST", "/projects", {"name": FLAGSHIP_NAME, "model": _dump(base)})
    fid = flagship["id"]
    owner.call("POST", f"/projects/{fid}/versions", {"label": "План для инвесткомитета"})
    owner.call("PUT", f"/projects/{fid}", {"model": _dump(stressed(base, d("0.93")))})
    owner.call("POST", f"/projects/{fid}/versions", {"label": "Стресс: цены сбыта −7%"})
    owner.call("PUT", f"/projects/{fid}", {"model": _dump(base)})
    cash = owner.call("POST", f"/projects/{fid}/calculate")["cashflow"]
    with_fact = base.model_copy(update={"actualization": flagship_actuals(
        {code: _line(cash, code) for code in ("C1", "C2")})})
    owner.call("PUT", f"/projects/{fid}", {"model": _dump(with_fact)})

    project_ids: dict[str, str] = {FLAGSHIP_NAME: fid}
    for template_id, name, months in TEMPLATE_PROJECTS:
        model = owner.call("GET", f"/templates/{template_id}")
        if months is not None:
            model = prolong(model, months)
        model["header"]["name"] = name
        project_ids[name] = owner.call("POST", "/projects", {"name": name,
                                                             "model": model})["id"]

    # 5. Холдинг: производство — головная, перевозки и магазин — дочерние.
    holding = owner.call("POST", "/holdings", {"name": "Группа «Демо»"})
    owner.call("POST", f"/holdings/{holding['id']}/members",
               {"project_id": fid, "role": "parent"})
    for name in (LOGISTICS_NAME, RETAIL_NAME):
        owner.call("POST", f"/holdings/{holding['id']}/members",
                   {"project_id": project_ids[name], "role": "subsidiary"})
    owner.call("POST", f"/holdings/{holding['id']}/consolidate")

    # 6. Обсуждение у отчёта: вопрос владельца с упоминанием и ответ аналитика.
    owner.call("POST", f"/projects/{fid}/comments", {
        "body": f"@{ANALYST.email} посмотри долю ЛЛДПЭ в себестоимости: поставщик "
                "предупредил о росте цены полимера с IV квартала.",
        "anchor": "report:income", "anchor_label": "Прибыли и убытки"})
    analyst.call("POST", f"/projects/{fid}/comments", {
        "body": "Инфляция прямых издержек заложена 6% в год. Проверю чувствительность NPV "
                "к цене сырья на вкладке «Чувствительность» и отпишусь здесь.",
        "anchor": "report:income", "anchor_label": "Прибыли и убытки"})

    # 7. «Финанс-Аудит»: демо-дело продукта и две фирмы-цели, группа, справочники.
    owner.call("POST", "/audit/subjects/demo")
    case_ids: dict[str, str] = {}
    for name, build in AUDIT_CASES:
        case_ids[name] = owner.call("POST", "/audit/subjects",
                                    {"name": name, "model": build()})["id"]
    tl_id = case_ids[AUDIT_CASES[0][0]]
    owner.call("POST", "/audit/groups", {"name": "Перевозчик + агро (свод)", "model": {
        "members": [{"subject_id": cid, "name": name} for name, cid in case_ids.items()]}})
    owner.call("PUT", f"/organizations/{org_id}/benchmarks", BENCHMARKS)
    owner.call("PUT", f"/organizations/{org_id}/checklists", CHECKLISTS)
    owner.call("POST", f"/audit/subjects/{tl_id}/versions",
               {"label": "Перед инвесткомитетом 15.09"})
    analyst.call("POST", f"/audit/subjects/{tl_id}/comments", {
        "body": "Дебиторка перевозчика-банкрота переоценена на −3,5 млн ₽ (2025). Реестр "
                "расходится с балансом на 56 млн ₽ — это кредиторка поставщикам, процентного "
                "долга в ней нет. Ковенант Сбербанка соблюдён: Долг/EBITDA ≈ 154/107 ≈ 1,4 "
                "при пороге 3,0.",
        "anchor": "tab:obligations", "anchor_label": "Обязательства"})

    # 8. Самопроверка: каждый проект считается, баланс сходится помесячно.
    projects = [_check_project(owner, pid, name) for name, pid in project_ids.items()]
    cases = []
    for name, cid in case_ids.items():
        summary = owner.call("POST", f"/audit/subjects/{cid}/analyze")["summary"]
        cases.append(CaseCheck(
            name=name, verdict=summary["verdict"], headline=summary["headline"],
            risk_flags=summary["risk_flags"], warning_flags=summary["warning_flags"],
            equity_value=_money(summary.get("equity_value")),
            asking_price=_money(summary.get("asking_price"))))
    return SeedReport(org_id=org_id, org_name=DEMO_ORG_NAME, accounts=accounts,
                      projects=projects, cases=cases, notes=notes)
