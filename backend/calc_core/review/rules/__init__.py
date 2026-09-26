"""Реестр правил ревью. Наполняется по фазам (R1+) из модулей категорий."""
from __future__ import annotations

from collections.abc import Callable

from ..config import ReviewConfig
from ..types import Finding, ReviewContext
from . import assumptions, divergence, liquidity, structure, viability

Rule = Callable[[ReviewContext, ReviewConfig], list[Finding]]

# По мере добавления категорий сюда добавляются *<модуль>.RULES.
RULES: list[Rule] = [
    *viability.RULES, *liquidity.RULES, *structure.RULES, *assumptions.RULES,
    *divergence.RULES,
]
