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

    def monthly_rate(self) -> Decimal:
        # эквивалентная месячная ставка: (1+R)^(1/12) - 1
        return (Decimal(1) + self.annual_rate) ** (Decimal(1) / Decimal(12)) - Decimal(1)


class EquityInjection(BaseModel):
    """Взнос в акционерный капитал (обыкновенные акции)."""

    amount: Decimal
    month: int = 0


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
    equity: list[EquityInjection] = Field(default_factory=list)
    # Явные выплаты дивидендов по месяцам (v0). Политика по доле прибыли — следующая фаза.
    dividends: list[Decimal] = Field(default_factory=list)
    # Число обыкновенных акций (No) — для инвестиционных показателей «на акцию».
    common_shares: Decimal = Decimal(0)
    auto_financing: AutoFinancing = AutoFinancing()
