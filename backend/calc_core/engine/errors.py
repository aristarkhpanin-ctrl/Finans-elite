"""Ошибки расчётного ядра."""
from __future__ import annotations


class CalcError(Exception):
    """Базовая ошибка расчёта."""


class ModelError(CalcError):
    """Некорректная входная модель (например, несходящийся стартовый баланс)."""


class InvariantError(CalcError):
    """Нарушен внутренний инвариант расчёта (баг ядра) — например, баланс не сходится."""
