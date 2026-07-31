"""Канонизация результата анализа в простой словарь (golden-master Финанс-Аудит).

Как в первом продукте: суммы — до копеек (2 знака), коэффициенты/доли — до 6 знаков.
Снимок стабилен между платформами, диффы читаемы при ревью.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from calc_core.money import D, quantize

from .result import AuditResult

MONEY_PLACES = 2
RATIO_PLACES = 6

_RATIO_GROUPS = ("liquidity", "activity", "gearing", "profitability")


def _money(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else str(quantize(D(value), MONEY_PLACES))


def _ratio(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else str(quantize(D(value), RATIO_PLACES))


def result_to_dict(result: AuditResult) -> dict[str, object]:
    """Полный канонический снимок результата анализа."""
    return {
        "n": result.n,
        "periods": list(result.periods),
        "balance": [
            {"code": ln.code, "label": ln.label, "subtotal": ln.subtotal,
             "values": [_money(v) for v in ln.values]}
            for ln in result.balance
        ],
        "income": [
            {"code": ln.code, "label": ln.label, "subtotal": ln.subtotal,
             "values": [_money(v) for v in ln.values]}
            for ln in result.income
        ],
        "horizontal": [
            {"code": t.code, "delta": [_money(v) for v in t.delta],
             "rate": [_ratio(v) for v in t.rate]}
            for t in result.horizontal
        ],
        "vertical": [
            {"code": s.code, "share": [_ratio(v) for v in s.share]}
            for s in result.vertical
        ],
        "ratios": {
            group: {
                name: [_ratio(v) for v in series]
                for name, series in result.ratios.get(group, {}).items()
            }
            for group in _RATIO_GROUPS
        },
        "balance_gap": [_money(v) for v in result.balance_gap],
        "balanced": result.balanced,
        "diagnostics": _diagnostics_to_dict(result.diagnostics),
        "warnings": list(result.warnings),
    }


def _diagnostics_to_dict(d) -> Optional[dict[str, object]]:
    if d is None:
        return None
    return {
        "light": d.light,
        "summary": d.summary,
        "scores": [
            {"id": s.id, "name": s.name, "values": [_ratio(v) for v in s.values],
             "zones": list(s.zones), "note": s.note}
            for s in d.scores
        ],
        "assessments": [
            {"group": a.group, "name": a.name, "status": list(a.status)}
            for a in d.assessments
        ],
    }
