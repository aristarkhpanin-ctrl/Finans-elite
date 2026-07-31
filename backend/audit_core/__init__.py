"""Финанс-Аудит — ядро анализа фактической отчётности (продукт №2).

Фаза B — модель субъекта/периодов/отчётности. Аналитика (коэффициенты, тренды,
диагностика) — фаза C+. Ядро первого продукта (``calc_core``) не затрагивается.
"""
from __future__ import annotations

from .models import AuditPeriod, AuditSubjectModel

__all__ = ["AuditPeriod", "AuditSubjectModel"]
