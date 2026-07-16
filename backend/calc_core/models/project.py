"""Верхнеуровневая модель проекта (замена файла ``.pex``) — корень входных данных ядра.

Структура повторяет дерево из ARCHITECTURE-SaaS.md §5.3 и CALC-ENGINE-SPEC.md.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .actualization import Actualization
from .common import InventoryMethod, VatBasis
from .company import Company
from .environment import Environment
from .financing import Financing
from .investment import InvestmentPlan
from .operating import OperatingPlan
from .tables import UserTable


class ProjectHeader(BaseModel):
    """Заголовок/паспорт проекта."""

    name: str = "Без названия"
    start_date: date = date(2026, 1, 1)
    # Горизонт N задаёт длину всех временных рядов; верхняя граница (50 лет) защищает
    # от исчерпания памяти/зависания воркера на абсурдных входах (DoS).
    duration_months: int = Field(default=12, ge=1, le=600)


class PlanSection(BaseModel):
    """Текстовый раздел бизнес-плана (резюме, рынок, команда…) для DOCX-документа.

    Текст пользователя: к расчёту отношения не имеет (модель без разделов инертна).
    Границы длины — защита хранилища/генератора документа от абсурдных входов.
    """

    title: str = Field(default="", max_length=300)
    text: str = Field(default="", max_length=50_000)


class ProjectSettings(BaseModel):
    """Настройка расчёта (см. SPEC §11, §17)."""

    discount_rate_annual: Decimal = Decimal("0.15")   # ставка дисконтирования (для NPV)
    terminal_growth_rate: Decimal = Decimal("0")      # темп роста g для модели Гордона (§20)
    # Множитель к годовой чистой прибыли для оценки по мультипликатору (0 = выключено; §20).
    valuation_earnings_multiple: Decimal = Decimal("0")
    # Доля возврата активов при ликвидации (0..1; 0 = метод выключен; §20).
    liquidation_recovery_rate: Decimal = Decimal("0")
    profit_tax_rate: Decimal = Decimal("0.20")        # налог на прибыль
    # Доля налогооблагаемой прибыли, освобождаемая от налога (льгота, 0..1; SPEC §22.7).
    profit_tax_benefit_share: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    # Периодичность уплаты налога на прибыль и НДС (SPEC §11): месяц — в месяце начисления;
    # квартал/год — в последнем месяце периода, отсрочка → B21. Начисление не меняют.
    profit_tax_periodicity: Literal["month", "quarter", "year"] = "month"
    vat_periodicity: Literal["month", "quarter", "year"] = "month"
    # Нормирование процентов (SPEC §11): годовая ставка рефинансирования ЦБ
    # (0 = норматив выключен) и законный коэффициент. Вычитаемы проценты в пределах
    # ставка_ЦБ × коэффициент; сверхнорматив относится на прибыль (I24).
    cb_refinancing_rate: Decimal = Field(default=Decimal("0"), ge=0)
    interest_norm_multiple: Decimal = Field(default=Decimal("1"), ge=0)
    # Страховые взносы с ФОТ (доля): загружают затраты на персонал (SPEC §8, §11).
    payroll_contribution_rate: Decimal = Field(default=Decimal("0"), ge=0)
    # Годовая инфляция по группам (SPEC §3): индексирует введённые (базовые) суммы.
    inflation_sales: Decimal = Decimal("0")      # цены сбыта
    inflation_direct: Decimal = Decimal("0")     # прямые материальные издержки
    inflation_wages: Decimal = Decimal("0")      # зарплата (сдельная + персонал)
    inflation_general: Decimal = Decimal("0")    # общие (постоянные) издержки
    # Погодовые ряды инфляции (SPEC §3): непустой ряд переопределяет скаляр; год k → series[k],
    # за пределом ряда — последнее значение. Пустой ряд → скаляр (обратная совместимость).
    inflation_sales_series: list[Decimal] = Field(default_factory=list)
    inflation_direct_series: list[Decimal] = Field(default_factory=list)
    inflation_wages_series: list[Decimal] = Field(default_factory=list)
    inflation_general_series: list[Decimal] = Field(default_factory=list)
    property_tax_rate: Decimal = Decimal("0")         # налог на имущество (база — B11)
    sales_tax_rate: Decimal = Decimal("0")            # налог с продаж/акциз (база — I1, не НДС)
    vat_rate: Decimal = Decimal("0")                  # ставка НДС (0 = НДС выключен)
    vat_basis: VatBasis = VatBasis.SHIPMENT           # момент признания НДС (SPEC §22.2)
    inventory_method: InventoryMethod = InventoryMethod.AVERAGE  # оценка ГП (SPEC §22.8)
    # Длительность производственного цикла (мес.): задержка между запуском в производство
    # (расход материалов/труда) и выпуском ГП; стоимость в пути копится в НЗП — B4 (SPEC §6).
    production_cycle_months: int = Field(default=0, ge=0)
    min_cash_balance: Decimal = Decimal("0")          # мин. остаток (для автоподбора, далее)


class ProjectModel(BaseModel):
    """Полная модель проекта."""

    header: ProjectHeader = ProjectHeader()
    settings: ProjectSettings = ProjectSettings()
    company: Company = Company()
    environment: Environment = Environment()
    investment_plan: InvestmentPlan = InvestmentPlan()
    operating_plan: OperatingPlan = OperatingPlan()
    financing: Financing = Financing()
    actualization: Actualization = Actualization()
    # Таблицы пользователя (строки-формулы над результатом; методику не меняют).
    user_tables: list[UserTable] = Field(default_factory=list)
    # Текстовые разделы бизнес-плана для DOCX-документа (пакет №5; к расчёту не относятся).
    business_plan: list[PlanSection] = Field(default_factory=list, max_length=100)

    @property
    def n(self) -> int:
        """Число месяцев расчёта."""
        return self.header.duration_months
