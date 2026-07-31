"""Финанс-Аудит — ядро анализа фактической отчётности (продукт №2).

Фаза B — модель субъекта/периодов/отчётности; фаза C — аналитика (аналитическая форма,
горизонтальный/вертикальный анализ, коэффициенты). Диагностика банкротства — фаза D.
Ядро первого продукта (``calc_core``) не затрагивается.
"""
from __future__ import annotations

from .analysis import analyze
from .models import AuditPeriod, AuditSubjectModel
from .result import AuditLine, AuditResult, ShareLine, TrendLine

__all__ = [
    "AuditLine",
    "AuditPeriod",
    "AuditResult",
    "AuditSubjectModel",
    "ShareLine",
    "TrendLine",
    "analyze",
]
