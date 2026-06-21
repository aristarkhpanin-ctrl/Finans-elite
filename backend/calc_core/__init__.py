"""calc_core — изолированное расчётное ядро финансовой модели.

Чистая детерминированная функция ``run(model) -> CalcResult`` без зависимостей от БД,
HTTP и арендаторов (см. ARCHITECTURE-SaaS.md §6, CALC-ENGINE-SPEC.md).
"""
from __future__ import annotations

from .engine import CalcOptions, CalcError, InvariantError, ModelError, run
from .models import ProjectModel
from .reports import CalcResult
from .version import ENGINE_VERSION

__all__ = [
    "run",
    "CalcOptions",
    "ProjectModel",
    "CalcResult",
    "ENGINE_VERSION",
    "CalcError",
    "ModelError",
    "InvariantError",
]
