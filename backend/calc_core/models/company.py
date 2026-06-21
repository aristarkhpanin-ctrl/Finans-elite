"""Компания: стартовый баланс (см. SPEC §1, §14).

В v0 стартовый баланс задаётся агрегированно; полный набор статей (≈20) добавляется
по мере развития ядра. Опорное требование: стартовый баланс должен сходиться
(актив = пассив), иначе ядро поднимет ошибку модели.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class StartingBalance(BaseModel):
    """Начальное состояние действующего предприятия (на конец периода t = -1)."""

    cash: Decimal = Decimal(0)                 # → B1
    fixed_assets_net: Decimal = Decimal(0)     # → B11 (остаточная стоимость ОС)
    foreign_monetary: Decimal = Decimal(0)     # монетарный актив во 2-й валюте, ед. валюты → B6
    debt: Decimal = Decimal(0)                 # → B26 (долгосрочные займы)
    paid_in_capital: Decimal = Decimal(0)      # → B27 (обыкновенные акции)
    retained_earnings: Decimal = Decimal(0)    # → B32 (нераспределённая прибыль)

    def assets(self) -> Decimal:
        return self.cash + self.fixed_assets_net

    def liabilities_equity(self) -> Decimal:
        return self.debt + self.paid_in_capital + self.retained_earnings


class Company(BaseModel):
    starting_balance: StartingBalance = StartingBalance()
