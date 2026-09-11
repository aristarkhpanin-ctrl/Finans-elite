"""Ревью бизнес-плана — детерминированный «линтер модели».

Публичный вход: ``run_review(ReviewContext(model, result)) -> ReviewResult``.
"""
from __future__ import annotations

from .config import DEFAULT_CONFIG, ReviewConfig
from .runner import run_review
from .types import Finding, ReviewContext, ReviewResult, Severity

__all__ = [
    "DEFAULT_CONFIG",
    "ReviewConfig",
    "run_review",
    "Finding",
    "ReviewContext",
    "ReviewResult",
    "Severity",
]
