"""Автоподбор финансирования: кредитная линия для покрытия дефицита наличности (SPEC §19).

Связь проценты ↔ прибыль ↔ налог ↔ деньги делает задачу итеративной: проценты по
автокредиту уменьшают прибыль и налог, меняя денежный поток, от которого зависит размер
привлечения. Итерация сходится, так как обратная связь идёт через налог (доля < 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..money import ZERO
from ..series import zeros


@dataclass
class AutoInjection:
    """Добавки автофинансирования к строкам отчётов.

    Кредит: ``pl_interest`` → проценты в ОПУ (I18, для налога); ``cash_*`` → денежные
    потоки (C22 займы, C23 погашение, C24 проценты) и краткосрочный долг B22.
    Депозит (авторазмещение): ``pl_deposit_income`` → доход в ОПУ (I20, для налога)
    отдельно от кассы; ``cash_deposit_income`` → C9; ``cash_deposit_placement`` → C8
    (размещение +, изъятие −); ``deposit_balance`` → B6 (тело на конец периода).
    Раздельность P&L/кассы депозита нужна пробному прогону: там доход учитывается в
    налоге (I20), но не в кассе (её считает решатель) — как процент кредита (I18 vs C24).
    """

    pl_interest: list[Decimal]
    cash_draws: list[Decimal]
    cash_principal: list[Decimal]
    cash_interest: list[Decimal]
    pl_deposit_income: list[Decimal] = field(default_factory=list)
    cash_deposit_income: list[Decimal] = field(default_factory=list)
    cash_deposit_placement: list[Decimal] = field(default_factory=list)
    deposit_balance: list[Decimal] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Депозитные ряды по умолчанию — нули той же длины (кредит-only инъекция инертна).
        n = len(self.pl_interest)
        for name in ("pl_deposit_income", "cash_deposit_income",
                     "cash_deposit_placement", "deposit_balance"):
            if not getattr(self, name):
                setattr(self, name, zeros(n))

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


@dataclass
class CashPlan:
    """График управления кассой: кредитная линия + авторазмещение излишков."""

    draws: list[Decimal]              # привлечение кредита → C22
    principal: list[Decimal]          # погашение тела кредита → C23
    interest: list[Decimal]           # проценты по кредиту → I18/C24
    deposit_placement: list[Decimal]  # размещение (+) / изъятие (−) депозита → C8
    deposit_income: list[Decimal]     # доход по депозиту → I20/C9
    deposit_balance: list[Decimal]    # тело депозита на конец периода → B6


def solve_cash_management(base_flow: list[Decimal], opening_cash: Decimal,
                          min_balance: Decimal, credit_rate: Decimal, deposit_rate: Decimal,
                          *, credit_on: bool, invest_on: bool) -> CashPlan:
    """Единый решатель кассы: кредит покрывает дефицит, депозит копит излишки (SPEC §19).

    Проценты по кредиту и доход по депозиту начисляются на остатки **начала периода**.
    При дефиците: сперва изъятие депозита, затем привлечение кредита; при профиците:
    сперва погашение кредита, затем размещение в депозит. При ``invest_on=False`` и
    ``credit_on=True`` результат совпадает с :func:`solve_credit_line` (equivalence-тест).
    """
    n = len(base_flow)
    draws = zeros(n)
    principal = zeros(n)
    interest = zeros(n)
    placement = zeros(n)
    income = zeros(n)
    dep_bal_series = zeros(n)
    cash = opening_cash
    credit = ZERO       # непогашенный остаток кредитной линии
    deposit = ZERO      # тело размещённого депозита
    for t in range(n):
        it = credit * credit_rate            # проценты на остаток кредита (начало периода)
        inc = deposit * deposit_rate         # доход на остаток депозита (начало периода)
        interest[t] = it
        income[t] = inc
        cash = cash + base_flow[t] - it + inc
        if cash < min_balance:
            need = min_balance - cash
            if deposit > 0:                  # сперва изымаем депозит
                withdraw = min(need, deposit)
                placement[t] -= withdraw
                deposit -= withdraw
                cash += withdraw
                need -= withdraw
            if need > 0 and credit_on:       # остаток дефицита — кредитом
                draws[t] = need
                credit += need
                cash += need
        elif cash > min_balance:
            surplus = cash - min_balance
            if credit > 0:                   # сперва гасим кредит
                repay = min(surplus, credit)
                principal[t] = repay
                credit -= repay
                cash -= repay
                surplus -= repay
            if surplus > 0 and invest_on:    # остаток профицита — в депозит
                placement[t] += surplus
                deposit += surplus
                cash -= surplus
        dep_bal_series[t] = deposit
    return CashPlan(draws=draws, principal=principal, interest=interest,
                    deposit_placement=placement, deposit_income=income,
                    deposit_balance=dep_bal_series)
