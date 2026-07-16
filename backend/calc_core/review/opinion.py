"""Экспертное заключение: связный автотекст из ревью и показателей (пакет №5, D0).

Детерминированные шаблонные абзацы над уже посчитанными фактами (как «экспертное
заключение» PE) — без ИИ. Используется в ответе ревью и в DOCX-бизнес-плане.
"""
from __future__ import annotations

from decimal import Decimal

from ..reports.result import CalcResult
from .text import fmt_pct, fmt_rub
from .types import ReviewResult

_LIGHT_INTRO = {
    "ok": "Ревью бизнес-плана не выявило рисков и предупреждений: ключевые показатели "
          "согласованы, модель возражений не вызывает.",
    "info": "Ревью бизнес-плана не выявило существенных рисков; отмечены отдельные "
            "допущения, которые стоит перепроверить.",
    "warning": "Ревью бизнес-плана выявило слабые места: до финализации рекомендуется "
               "усилить перечисленные позиции.",
    "risk": "Ревью бизнес-плана выявило существенные риски: в текущем виде план требует "
            "доработки, финализация возможна только с их осознанным принятием.",
}


def _metrics_paragraph(result: CalcResult) -> str:
    m = result.metrics
    parts: list[str] = []
    parts.append(f"Чистая приведённая стоимость (NPV) проекта за {result.n} мес. составляет "
                 f"{fmt_rub(m.npv)} ₽")
    if m.irr_annual is not None:
        parts.append(f"внутренняя норма доходности (IRR) — {fmt_pct(m.irr_annual)} годовых")
    else:
        parts.append("внутренняя норма доходности (IRR) не определена")
    if m.pb_months is not None:
        parts.append(f"простая окупаемость достигается на {m.pb_months}-м месяце")
    else:
        parts.append("окупаемость в пределах горизонта не достигается")
    if m.peak_financing_need is not None and m.peak_financing_need > 0:
        parts.append(f"пиковая потребность в финансировании — {fmt_rub(m.peak_financing_need)} ₽")
    return ". ".join((parts[0] + "; " + "; ".join(parts[1:])).split("\n")) + "."


def _findings_block(review: ReviewResult, severity: str, title: str, limit: int = 5) -> str:
    rows = [f for f in review.findings if f.severity == severity][:limit]
    if not rows:
        return ""
    lines = [title]
    for f in rows:
        lines.append(f"— {f.title}. {f.recommendation}")
    return "\n".join(lines)


def build_opinion(review: ReviewResult, result: CalcResult) -> str:
    """Собрать текст заключения: вывод + показатели + риски/предупреждения + рекомендация."""
    blocks: list[str] = [
        _LIGHT_INTRO.get(review.light, _LIGHT_INTRO["info"]),
        _metrics_paragraph(result),
    ]
    risks = _findings_block(review, "risk", "Существенные риски:")
    if risks:
        blocks.append(risks)
    warnings = _findings_block(review, "warning", "Слабые места (предупреждения):")
    if warnings:
        blocks.append(warnings)

    npv = result.metrics.npv
    counts = review.counts
    if review.light == "risk" or npv < 0:
        verdict = ("Итог: план в текущем виде не рекомендуется к реализации без устранения "
                   "перечисленных рисков и пересмотра ключевых допущений.")
    elif review.light == "warning":
        verdict = ("Итог: план жизнеспособен, но рекомендуется закрыть перечисленные слабые "
                   "места до привлечения финансирования.")
    else:
        verdict = "Итог: план согласован и готов к представлению инвестору/банку."
    if counts.get("info", 0) and review.light in ("ok", "info"):
        verdict += f" Заметок для перепроверки: {counts['info']}."
    blocks.append(verdict)
    return "\n\n".join(blocks)


def opinion_is_positive(review: ReviewResult, npv: Decimal) -> bool:
    """Позитивно ли заключение (для тестов/UI-тональности)."""
    return review.light in ("ok", "info") and npv >= 0
