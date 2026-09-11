"""Настраиваемые налоги (SPEC §22.9, gap 2.1): база × ставка → начисление, уплата, B21.

Базы вычисляются по **предварительному прогону** конвейера (без настраиваемых налогов
и автоподбора финансирования) — один детерминированный проход без циклов «налог ←
база ← налог». Ошибка формулы базы — ``ModelError`` (расчёт отклоняется): молча
нулевой налог в финансовой модели недопустим. Пустой список налогов инертен.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..formula import FormulaError, evaluate
from ..formula.functions import as_series
from ..models import ProjectModel
from ..money import ZERO
from ..reports.statements import Statement
from ..series import zeros
from .errors import ModelError

#: Пресеты баз — формулы над строками предварительного прогона (решение Q2).
BASE_FORMULAS = {
    "revenue": "I1",
    "payroll": "I6 + I13 + I14 + I15",   # загруженный ФОТ (вкл. взносы), сдельная + персонал
    "property": "B13 + B14",             # амортизируемое имущество (как база I9)
    "profit": "МАКС(I26, 0)",            # положительная налогооблагаемая прибыль
}

#: Длина периода уплаты в месяцах (месяц — уплата в месяце начисления).
_PERIOD_MONTHS = {"month": 1, "quarter": 3, "year": 12}


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


def _payment_schedule(accrual: list[Decimal], periodicity: str, n: int) -> list[Decimal]:
    """Уплата по периодичности: в последнем месяце периода проекта — накопленное.

    Хвост неполного периода остаётся неуплаченным (честная задолженность в B21);
    принудительного закрытия в конце горизонта нет (решение Q5).
    """
    size = _PERIOD_MONTHS[periodicity]
    if size == 1:
        return list(accrual)
    paid = zeros(n)
    acc = ZERO
    for t in range(n):
        acc += accrual[t]
        if t % size == size - 1:
            paid[t] = acc
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
    for tax in model.environment.taxes:
        expr = tax.formula if tax.base == "formula" else BASE_FORMULAS[tax.base]
        try:
            base = as_series(evaluate(expr, env, n), n)
        except FormulaError as exc:
            raise ModelError(f"Налог «{tax.name}»: ошибка базы — {exc}") from exc
        accrual = [base[t] * tax.rate for t in range(n)]
        paid = _payment_schedule(accrual, tax.periodicity, n)
        target = inj.expense if tax.allocation == "expense" else inj.profit
        outstanding = ZERO
        for t in range(n):
            target[t] += accrual[t]
            inj.cash[t] += paid[t]
            outstanding += accrual[t] - paid[t]
            inj.deferred[t] += outstanding
        inj.cash_items.append((tax.name, paid))
    return inj
