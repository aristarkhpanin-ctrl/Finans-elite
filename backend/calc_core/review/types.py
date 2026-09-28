"""Типы этапа ревью бизнес-плана (детерминированный «линтер модели»).

См. docs/REVIEW-ADVISOR-DECOMPOSITION.md. Ревью — чтение результата расчёта; методику
расчёта не меняет (golden-master движка не затрагивается).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..models import ProjectModel
from ..montecarlo import MonteCarloResult
from ..reports.result import CalcResult
from ..sensitivity import SensitivityPoint

Severity = Literal["info", "warning", "risk"]
Category = Literal["viability", "liquidity", "structure", "assumptions", "divergence"]
Confidence = Literal["high", "medium", "low"]

#: Порядок серьёзности для сортировки/«светофора».
SEVERITY_ORDER: dict[str, int] = {"risk": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Finding:
    """Одна находка ревью (как запись линтера): доказана числом в ``evidence``."""

    id: str                       # стабильный код правила, напр. "liquidity.cash_gap"
    category: Category
    severity: Severity
    title: str
    detail: str
    recommendation: str
    confidence: Confidence = "high"
    evidence: dict = field(default_factory=dict)


@dataclass
class ReviewResult:
    """Итог ревью: «светофор» (худшая severity или ok), счётчики и находки."""

    light: str                    # "risk" | "warning" | "info" | "ok"
    counts: dict[str, int]
    findings: list[Finding]


@dataclass
class ReviewContext:
    """Вход правил: модель + результат расчёта (+ опц. стохастика для divergence)."""

    model: ProjectModel
    result: CalcResult
    mc: MonteCarloResult | None = None
    sensitivity: dict[str, list[SensitivityPoint]] | None = None
