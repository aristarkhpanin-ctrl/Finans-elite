"""Финансирование: займы, акционерный капитал, дивиденды (см. SPEC §10).

В v0 проценты начисляются на остаток тела по месячной ставке; погашение — равными
долями тела или единовременно в конце срока. Лизинг, автоподбор, льготы — следующие фазы.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from .common import RepaymentType


class Loan(BaseModel):
    """Заём."""

    name: str
    amount: Decimal                         # сумма поступления (→ C22)
    start_month: int = 0                    # месяц поступления
    term_months: int = 12                   # срок (месяцев)
    annual_rate: Decimal = Decimal("0.20")  # годовая ставка
    repayment: RepaymentType = RepaymentType.EQUAL_PRINCIPAL
    # Проценты «на прибыль» (невычитаемые): идут в I24, а не в I18 (см. SPEC §12, §22.1).
    interest_on_profit: bool = False
    # Заём во 2-й валюте: сумма/проценты/тело в валюте, пересчёт по FX[t]; долг
    # переоценивается → курсовая разница I25 (SPEC §22.3). По умолчанию — основная валюта.
    foreign: bool = False

    def monthly_rate(self) -> Decimal:
        # эквивалентная месячная ставка: (1+R)^(1/12) - 1
        return (Decimal(1) + self.annual_rate) ** (Decimal(1) / Decimal(12)) - Decimal(1)


class EquityInjection(BaseModel):
    """Взнос в акционерный капитал (обыкновенные акции)."""

    amount: Decimal
    month: int = 0


class Lease(BaseModel):
    """Лизинг (SPEC §10).

    **Операционный** (по умолчанию): платёж — целиком издержка (I21) и отток (C25).
    **Финансовый** (``finance=True``): предмет лизинга капитализируется (B19) и
    амортизируется (I17), обязательство (→ B26) гасится телом платежа, процентная часть —
    в I18. Приведённая стоимость платежей дисконтируется по ``annual_rate`` (ставка 0 —
    обязательство = сумме платежей без процентов).
    """

    name: str
    monthly_payment: Decimal
    start_month: int = 0
    term_months: int = 12
    finance: bool = False                   # финансовый лизинг (капитализация предмета)
    annual_rate: Decimal = Decimal("0")     # ставка для финансового лизинга (PV платежей)

    def monthly_rate(self) -> Decimal:
        return (Decimal(1) + self.annual_rate) ** (Decimal(1) / Decimal(12)) - Decimal(1)


class Deposit(BaseModel):
    """Размещение свободных средств: вложение C8, доход C9, тело в B6 (SPEC §10)."""

    name: str
    amount: Decimal                         # сумма размещения
    start_month: int = 0                    # месяц размещения
    term_months: int = 12                   # срок (возврат тела в start+term)
    annual_rate: Decimal = Decimal("0")     # годовая ставка дохода


class AutoFinancing(BaseModel):
    """Автоподбор финансирования: покрытие дефицита наличности кредитной линией.

    Каждый период, если денег меньше ``min_balance``, привлекается заём до этого уровня;
    при профиците задолженность гасится. Проценты влияют на прибыль и налог, поэтому
    расчёт итеративный (см. SPEC §19).
    """

    enabled: bool = False
    annual_rate: Decimal = Decimal("0.18")  # годовая ставка кредитной линии
    min_balance: Decimal = Decimal("0")     # минимальный остаток денежных средств


class Financing(BaseModel):
    loans: list[Loan] = Field(default_factory=list)
    leases: list[Lease] = Field(default_factory=list)
    deposits: list[Deposit] = Field(default_factory=list)
    equity: list[EquityInjection] = Field(default_factory=list)
    # Явные выплаты дивидендов по месяцам (v0). Политика по доле прибыли — следующая фаза.
    dividends: list[Decimal] = Field(default_factory=list)
    # Число обыкновенных акций (No) — для инвестиционных показателей «на акцию».
    common_shares: Decimal = Decimal(0)
    auto_financing: AutoFinancing = AutoFinancing()
