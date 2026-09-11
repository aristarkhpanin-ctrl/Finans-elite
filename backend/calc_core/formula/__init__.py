"""Язык формул над помесячными рядами (таблицы пользователя; SPEC «Язык формул»).

Безопасный (без ``eval``) парсер + вычислитель на Decimal с лимитами сложности.
См. docs/FORMULA-TABLES-DECOMPOSITION.md.
"""
from .evaluator import Env, evaluate
from .functions import ALIASES, FUNCTIONS, Value
from .parser import FormulaError, parse

__all__ = ["evaluate", "parse", "FormulaError", "FUNCTIONS", "ALIASES", "Env", "Value"]
