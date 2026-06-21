"""Автоподбор финансирования: кредитная линия для покрытия дефицита наличности (SPEC §19).

Связь проценты ↔ прибыль ↔ налог ↔ деньги делает задачу итеративной: проценты по
автокредиту уменьшают прибыль и налог, меняя денежный поток, от которого зависит размер
привлечения. Итерация сходится, так как обратная связь идёт через налог (доля < 1).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..money import ZERO
from ..series import zeros


@dataclass
class AutoInjection:
    """Добавки автофинансирования к строкам отчётов.

    ``pl_interest`` → проценты в ОПУ (I18, для налога); ``cash_*`` → денежные потоки
    (C22 займы, C23 погашение, C24 проценты) и краткосрочный долг B22.
    """

    pl_interest: list[Decimal]
    cash_draws: list[Decimal]
    cash_principal: list[Decimal]
    cash_interest: list[Decimal]

    @staticmethod
    def zero(n: int) -> "AutoInjection":
        return AutoInjection(zeros(n), zeros(n), zeros(n), zeros(n))


def solve_credit_line(base_flow: list[Decimal], opening_cash: Decimal,
                      min_balance: Decimal, monthly_rate: Decimal):
    """Рассчитать график кредитной линии по денежному потоку до автофинансирования.

    ``base_flow[t]`` — изменение денег за период (операционная + инвестиционная +
    ручная финансовая деятельность, с учётом налога). Возвращает ``(draws, principal,
    interest)`` — привлечение, погашение тела и проценты по месяцам.
    """
    n = len(base_flow)
    draws = zeros(n)
    principal = zeros(n)
    interest = zeros(n)
    cash = opening_cash
    balance = ZERO  # непогашенный остаток кредитной линии
    for t in range(n):
        it = balance * monthly_rate          # проценты на остаток на начало периода
        interest[t] = it
        cash = cash + base_flow[t] - it
        if cash < min_balance:
            draw = min_balance - cash        # привлечь до минимального остатка
            draws[t] = draw
            balance += draw
            cash = min_balance
        elif balance > 0:
            repay = min(cash - min_balance, balance)  # гасить из профицита
            principal[t] = repay
            balance -= repay
            cash -= repay
    return draws, principal, interest
