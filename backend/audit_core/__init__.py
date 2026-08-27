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
from .models import AuditPeriod, AuditSubjectModel
from .result import AuditLine, AuditResult, ShareLine, TrendLine

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
    "ShareLine",
    "TrendLine",
    "analyze",
    "check_input",
    "detect_flags",
    "normalize_earnings",
    "consolidate_subjects",
]
