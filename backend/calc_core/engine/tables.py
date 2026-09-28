"""Таблицы пользователя: вычисление строк-формул над готовым результатом (SPEC «Язык формул»).

Считаются **после** расчёта отчётов (методику не меняют, как ревью). Ошибка формулы не
роняет расчёт: строка получает сообщение и нулевой ряд. Окружение — все строки четырёх
отчётов по кодам (I*, C*, B*, P*) + горизонт ``N``.
"""
from __future__ import annotations

from decimal import Decimal

from ..formula import FormulaError, evaluate
from ..formula.functions import as_series
from ..models.project import ProjectModel
from ..reports.result import UserRowResult, UserTableResult
from ..reports.statements import Statement
from ..series import zeros


def _environment(income: Statement, cashflow: Statement, balance: Statement,
                 profit_use: Statement, n: int) -> dict[str, list[Decimal] | Decimal]:
    env: dict[str, list[Decimal] | Decimal] = {}
    for stmt in (income, cashflow, balance, profit_use):
        for code in stmt.order:
            env[code] = stmt[code]
    env["N"] = Decimal(n)
    return env


def compute_user_tables(model: ProjectModel, income: Statement, cashflow: Statement,
                        balance: Statement, profit_use: Statement,
                        n: int) -> list[UserTableResult]:
    """Вычислить все таблицы пользователя; пустой список таблиц → пустой результат."""
    if not model.user_tables:
        return []
    env = _environment(income, cashflow, balance, profit_use, n)
    out: list[UserTableResult] = []
    for table in model.user_tables:
        rows: list[UserRowResult] = []
        for row in table.rows:
            try:
                value = evaluate(row.formula, env, n)
                rows.append(UserRowResult(name=row.name, values=as_series(value, n)))
            except FormulaError as exc:
                rows.append(UserRowResult(name=row.name, values=zeros(n), error=str(exc)))
        out.append(UserTableResult(id=table.id, name=table.name, rows=rows))
    return out
