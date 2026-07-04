"""Прогон реестра правил → ReviewResult («светофор», счётчики, отсортированные находки)."""
from __future__ import annotations

from .config import DEFAULT_CONFIG, ReviewConfig
from .rules import RULES
from .types import SEVERITY_ORDER, Finding, ReviewContext, ReviewResult


def run_review(ctx: ReviewContext, config: ReviewConfig = DEFAULT_CONFIG) -> ReviewResult:
    """Прогнать все правила по контексту и собрать итог.

    Детерминированно: правила — чистые функции над результатом расчёта. «Светофор» —
    худшая severity среди находок (``ok``, если находок нет).
    """
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(ctx, config))
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.id))
    counts = {"risk": 0, "warning": 0, "info": 0}
    for finding in findings:
        counts[finding.severity] += 1
    light = next((s for s in ("risk", "warning", "info") if counts[s]), "ok")
    return ReviewResult(light=light, counts=counts, findings=findings)
