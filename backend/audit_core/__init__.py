"""Финанс-Аудит — ядро анализа фактической отчётности (продукт №2).

Фаза B — модель субъекта/периодов/отчётности; фаза C — аналитика (аналитическая форма,
горизонтальный/вертикальный анализ, коэффициенты). Диагностика банкротства — фаза D.
Ядро первого продукта (``calc_core``) не затрагивается.
"""
from __future__ import annotations

from .analysis import analyze
from .consolidate import Consolidation, Elimination, consolidate_subjects
from .earnings import EarningsQuality, normalize_earnings
from .flags import Flag, FlagRegistry, detect_flags
from .input_check import InputIssue, check_input
from .models import AuditPeriod, AuditSubjectModel, Obligation
from .obligations import ObligationRegister, build_obligations
from .procedures import Procedure, ProcedureReport, run_procedures
from .result import AuditLine, AuditResult, ShareLine, TrendLine
from .risk import RiskResult, analyze_risk
from .summary import CaseSummary, build_summary
from .valuation import Valuation, build_valuation

__all__ = [
    "AuditLine",
    "Consolidation",
    "Elimination",
    "AuditPeriod",
    "AuditResult",
    "AuditSubjectModel",
    "EarningsQuality",
    "Flag",
    "FlagRegistry",
    "InputIssue",
    "Obligation",
    "ObligationRegister",
    "CaseSummary",
    "Procedure",
    "ProcedureReport",
    "RiskResult",
    "ShareLine",
    "TrendLine",
    "Valuation",
    "analyze",
    "analyze_risk",
    "build_obligations",
    "build_summary",
    "build_valuation",
    "check_input",
    "detect_flags",
    "run_procedures",
    "normalize_earnings",
    "consolidate_subjects",
]
