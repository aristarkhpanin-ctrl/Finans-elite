"""Финанс-Аудит — ядро анализа фактической отчётности (продукт №2).

Фаза B — модель субъекта/периодов/отчётности; фаза C — аналитика (аналитическая форма,
горизонтальный/вертикальный анализ, коэффициенты). Диагностика банкротства — фаза D.
Ядро первого продукта (``calc_core``) не затрагивается.
"""
from __future__ import annotations

from .analysis import analyze
from .consolidate import Consolidation, Elimination, consolidate_subjects
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
    "InputIssue",
    "ShareLine",
    "TrendLine",
    "analyze",
    "check_input",
    "consolidate_subjects",
]
