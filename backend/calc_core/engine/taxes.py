"""Настраиваемые налоги (SPEC §22.9, gap 2.1): база × ставка → начисление, уплата, B21.

Базы вычисляются по **предварительному прогону** конвейера (без настраиваемых налогов
и автоподбора финансирования) — один детерминированный проход без циклов «налог ←
база ← налог». Ошибка формулы базы — ``ModelError`` (расчёт отклоняется): молча
нулевой налог в финансовой модели недопустим. Пустой список налогов инертен.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, get_args

from ..formula import FormulaError, evaluate
from ..formula.functions import as_series
from ..models import ProjectModel
from ..money import ZERO
from ..reports.statements import TAX_YEAR_MONTHS, Statement, tax_year_offset
from ..series import zeros
from .errors import ModelError

#: Пресеты баз — формулы над строками предварительного прогона (решение Q2).
BASE_FORMULAS = {
    "revenue": "I1",
    "payroll": "I6 + I13 + I14 + I15",   # загруженный ФОТ (вкл. взносы), сдельная + персонал
    "property": "B13 + B14",             # амортизируемое имущество (как база I9)
    # Налогооблагаемая прибыль — прирост годовой нарастающей базы, как у профильного
    # налога (0.9.47). Не МАКС(I26, 0): внутри года прирост бывает отрицательным, и налог
    # поверх профильного, не сторнированный вместе с ним, переплачивался бы.
    "profit": "I26",
}

#: Длина периода уплаты в месяцах (месяц — уплата в месяце начисления). Год — тот же
#: налоговый (календарный) год, по которому ограничивается перенос убытков: конвенция одна.
_PERIOD_MONTHS = {"month": 1, "quarter": 3, "year": TAX_YEAR_MONTHS}


@dataclass
class TaxInjection:
    """Инъекция настраиваемых налогов в конвейер (нулевая — инертна)."""

    expense: list[Decimal]                 # начисление вычитаемых → I21
    profit: list[Decimal]                  # начисление за счёт прибыли → I24
    cash: list[Decimal]                    # уплата → C12
    deferred: list[Decimal]                # начислено − уплачено (конец периода) → B21
    # Пер-налоговые ряды уплаты — для детализации C12 (drill-down, пакет №6).
    cash_items: list[tuple[str, list[Decimal]]] = field(default_factory=list)

    @classmethod
    def zero(cls, n: int) -> TaxInjection:
        return cls(expense=zeros(n), profit=zeros(n), cash=zeros(n), deferred=zeros(n))


#: Правило срока уплаты (пакет J, J3). Обязательный аргумент :func:`_payment_schedule`:
#: прежняя конвенция «в последнем месяце периода» вернулась бы молча у того, кто его забыл.
#:
#: - ``next_month`` — в месяце, следующем за периодом (до 28-го числа; настраиваемые
#:   налоги, взносы и подобное);
#: - ``profit`` — налог на прибыль (ст. 287 НК РФ): авансы — в месяце, следующем за
#:   отчётным периодом; налог за год (период, кончающийся в декабре) — в марте;
#: - ``vat`` — НДС (ст. 174): за квартал — тремя равными долями в трёх следующих месяцах;
#:   месяц и год (упрощения модели, законом не предусмотренные) — в следующем месяце;
#: - ``property`` — налог на имущество (ст. 383): авансы — в месяце, следующем за
#:   кварталом; налог за год (период, кончающийся в декабре) — в феврале.
Due = Literal["next_month", "profit", "vat", "property"]
DUE_RULES: tuple[str, ...] = get_args(Due)


def _due_parts(due: Due, size: int, december: bool) -> list[tuple[int, int]]:
    """Сдвиги уплаты от последнего месяца периода: (через сколько месяцев, доля из 3)."""
    if due == "vat" and size == 3:
        return [(1, 1), (2, 1), (3, 1)]
    if due == "profit" and december:
        return [(3, 3)]
    if due == "property" and december:
        return [(2, 3)]
    return [(1, 3)]


def _payment_schedule(accrual: list[Decimal], periodicity: str, n: int, *,
                      offset: int, due: Due) -> list[Decimal]:
    """Уплата накопленного за **календарный** период — в срок по закону (пакет J, J3).

    ``offset`` — :func:`~calc_core.reports.statements.tax_year_offset` даты старта:
    квартал кончается в марте, июне, сентябре и декабре, год — в декабре (ст. 285, 163
    НК РФ). Первый период при старте не в январе неполный — он платится по сроку своего
    календарного периода. ``due`` — правило срока (``DUE_RULES``).

    До 0.9.51 налог платился в последнем месяце своего периода (при помесячной уплате — в
    месяце начисления), то есть на месяц раньше закона, а годовой налог на прибыль — на
    три месяца раньше. Уплата после конца горизонта остаётся задолженностью в B21 — как и
    хвост неполного периода (решение Q5: принудительного закрытия нет).

    Доли НДС — две трети по трети и остаток последней: сумма долей равна начисленному
    до копейки, иначе в B21 копилась бы пыль деления.
    """
    size = _PERIOD_MONTHS[periodicity]
    if due not in DUE_RULES:
        raise ValueError(f"Неизвестное правило срока уплаты: {due}")
    paid = zeros(n)
    acc = ZERO
    for t in range(n):
        acc += accrual[t]
        if (t + offset) % size != size - 1:
            continue
        parts = _due_parts(due, size, december=(t + offset) % 12 == 11)
        third = acc / 3
        left = acc
        for i, (lag, thirds) in enumerate(parts):
            amount = left if i == len(parts) - 1 else third * thirds
            left -= amount
            if t + lag < n:
                paid[t + lag] += amount
        acc = ZERO
    return paid


def compute_custom_taxes(model: ProjectModel, income: Statement, cashflow: Statement,
                         balance: Statement, profit_use: Statement, n: int) -> TaxInjection:
    """Начисление/уплата настраиваемых налогов над отчётами предварительного прогона."""
    env: dict[str, list[Decimal] | Decimal] = {}
    for stmt in (income, cashflow, balance, profit_use):
        for code in stmt.order:
            env[code] = stmt[code]
    env["N"] = Decimal(n)

    inj = TaxInjection.zero(n)
    offset = tax_year_offset(model.header.start_date)
    for tax in model.environment.taxes:
        expr = tax.formula if tax.base == "formula" else BASE_FORMULAS[tax.base]
        try:
            base = as_series(evaluate(expr, env, n), n)
        except FormulaError as exc:
            raise ModelError(f"Налог «{tax.name}»: ошибка базы — {exc}") from exc
        accrual = [base[t] * tax.rate for t in range(n)]
        paid = _payment_schedule(accrual, tax.periodicity, n, offset=offset,
                                 due="next_month")
        target = inj.expense if tax.allocation == "expense" else inj.profit
        outstanding = ZERO
        for t in range(n):
            target[t] += accrual[t]
            inj.cash[t] += paid[t]
            outstanding += accrual[t] - paid[t]
            inj.deferred[t] += outstanding
        inj.cash_items.append((tax.name, paid))
    return inj
