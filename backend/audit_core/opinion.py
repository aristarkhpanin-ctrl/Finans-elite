"""Экспертное заключение по анализу фактической отчётности (Финанс-Аудит, фаза E).

Детерминированный шаблонный текст над уже посчитанными фактами — **без ИИ** (как
заключение первого продукта). Структура (SPEC продукта №2, приложение Г):

1. интро по «светофору» состояния;
2. ключевые показатели последнего периода и их динамика;
3. находки — нарушенные нормативы и модели в зоне риска;
4. вердикт.

Формулировки опираются только на факты результата: если показатель не определён, он не
упоминается, а не подставляется нулём.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from calc_core.review.text import fmt_num, fmt_pct, fmt_rub

from .analysis import NET_PROFIT, TOTAL_ASSETS
from .diagnostics import DISTRESS, GREY, RISK, WARN
from .result import AuditResult

_LIGHT_INTRO = {
    "ok": "Анализ фактической отчётности не выявил признаков финансовой неустойчивости: "
          "ключевые показатели находятся в пределах нормативов.",
    "warning": "Анализ фактической отчётности не выявил критических нарушений, однако "
               "отдельные показатели находятся у границы нормативов и требуют внимания.",
    "risk": "Анализ фактической отчётности выявил признаки финансовой неустойчивости: "
            "ряд ключевых показателей находится вне нормативных значений.",
}

#: Показатели, выносимые в абзац «ключевые показатели» (группа, имя, формат).
_KEY_RATIOS: list[tuple[str, str, str]] = [
    ("liquidity", "Коэффициент текущей ликвидности", "num"),
    ("gearing", "Коэффициент автономии", "pct"),
    ("profitability", "Рентабельность чистой прибыли", "pct"),
    ("profitability", "Рентабельность собств. капитала (ROE)", "pct"),
]


def _fmt(value: Optional[Decimal], kind: str) -> Optional[str]:
    if value is None:
        return None
    return fmt_pct(value) if kind == "pct" else fmt_num(value)


def _line_values(result: AuditResult, code: str) -> list[Decimal]:
    for group in (result.balance, result.income):
        for ln in group:
            if ln.code == code:
                return ln.values
    return []


def _dynamics_phrase(values: list[Decimal], noun: str) -> Optional[str]:
    """Фраза о динамике показателя от первого к последнему периоду."""
    if len(values) < 2 or values[0] == 0:
        return None
    first, last = values[0], values[-1]
    change = (last - first) / abs(first)
    if abs(change) < Decimal("0.005"):
        return f"{noun} практически не изменилась"
    direction = "выросла" if change > 0 else "снизилась"
    return f"{noun} {direction} на {fmt_pct(abs(change))}"


def _key_ratios_sentence(result: AuditResult) -> str:
    last = result.n - 1
    parts: list[str] = []
    for group, name, kind in _KEY_RATIOS:
        series = result.ratios.get(group, {}).get(name)
        if not series:
            continue
        text = _fmt(series[last], kind)
        if text is not None:
            # строчная только первая буква — аббревиатуры (ROE, ROA) сохраняются
            parts.append(f"{name[0].lower() + name[1:]} — {text}")
    if not parts:
        return ""
    return ("По состоянию на последний период (" + result.periods[last] + "): "
            + "; ".join(parts) + ".")


def _dynamics_sentence(result: AuditResult) -> str:
    phrases: list[str] = []
    revenue = _line_values(result, "I_REVENUE")
    assets = _line_values(result, TOTAL_ASSETS)
    net = _line_values(result, NET_PROFIT)

    p = _dynamics_phrase(revenue, "выручка")
    if p:
        phrases.append(p)
    p = _dynamics_phrase(assets, "валюта баланса")
    if p:
        phrases.append(p)
    if len(net) >= 2:
        if net[-1] < 0:
            phrases.append("по итогам последнего периода получен убыток")
        elif net[0] < 0 <= net[-1]:
            phrases.append("предприятие вышло из убытка в прибыль")
    if not phrases:
        return ""
    return "За рассматриваемый период " + "; ".join(phrases) + "."


def _findings_block(result: AuditResult) -> str:
    """Нарушенные нормативы и модели в зоне риска (по последнему периоду)."""
    d = result.diagnostics
    if d is None:
        return ""
    last = result.n - 1
    lines: list[str] = []

    breached = [a.name for a in d.assessments if a.status and a.status[last] == RISK]
    if breached:
        lines.append("Вне нормативных значений:")
        lines.extend(f"— {name}" for name in breached[:6])

    warned = [a.name for a in d.assessments if a.status and a.status[last] == WARN]
    if warned and not breached:
        lines.append("У границы нормативов:")
        lines.extend(f"— {name}" for name in warned[:6])

    risky = [s.name for s in d.scores if s.zones and s.zones[last] == DISTRESS]
    grey = [s.name for s in d.scores if s.zones and s.zones[last] == GREY]
    if risky:
        models = ("Модели диагностики банкротства относят предприятие к зоне высокого "
                  "риска: " + ", ".join(risky) + ".")
    elif grey:
        models = ("Модели диагностики банкротства относят предприятие к зоне "
                  "неопределённости: " + ", ".join(grey) + ".")
    else:
        models = ""

    # Список нарушений и вывод моделей — отдельными абзацами (читаются раздельно).
    blocks = ["\n".join(lines)] if lines else []
    if models:
        blocks.append(models)
    return "\n\n".join(blocks)


def _verdict(result: AuditResult) -> str:
    d = result.diagnostics
    light = d.light if d is not None else "ok"
    net = _line_values(result, NET_PROFIT)
    loss = bool(net) and net[-1] < 0

    if light == "risk":
        base = ("Итог: финансовое состояние оценивается как неустойчивое. Требуются меры по "
                "восстановлению платёжеспособности и структуры капитала.")
    elif light == "warning":
        base = ("Итог: финансовое состояние в целом приемлемое; рекомендуется устранить "
                "отмеченные отклонения, не доводя их до критических значений.")
    else:
        base = ("Итог: финансовое состояние оценивается как устойчивое; критических "
                "отклонений не выявлено.")
    if loss and light != "risk":
        base += (" Обращает внимание убыток последнего периода — при его повторении оценка "
                 "состояния ухудшится.")
    return base


def _limits_block(procedures) -> str:
    """Границы проверки: что не проверялось и почему (SPEC, Приложение М.4).

    Раздел обязателен, когда чек-лист посчитан: заключение без границ читается как
    «проверено всё», а не проверено ровно то, что перечислено. Скрыть их нельзя —
    именно за это покупатель и платит.
    """
    if procedures is None or not procedures.limits:
        return ""
    coverage = procedures.coverage
    head = (f"Границы проверки. Выполнено процедур: {procedures.closed} из "
            f"{procedures.total}")
    if coverage is not None:
        head += f" ({coverage * 100:.0f}%)"
    head += ". Не выполнено:"
    return head + "\n" + "\n".join(f"— {line}" for line in procedures.limits)


def build_opinion(result: AuditResult, procedures=None) -> str:
    """Собрать текст экспертного заключения по результату анализа.

    ``procedures`` — отчёт чек-листа (``run_procedures``). Передан — в заключение
    попадает раздел «Границы проверки»; не передан — чек-лист не считался, и
    придумывать границы не из чего.
    """
    if result.n == 0:
        return "Недостаточно данных для заключения: не введены отчётные периоды."

    light = result.diagnostics.light if result.diagnostics is not None else "ok"
    blocks: list[str] = [_LIGHT_INTRO.get(light, _LIGHT_INTRO["warning"])]

    for sentence in (_key_ratios_sentence(result), _dynamics_sentence(result)):
        if sentence:
            blocks.append(sentence)

    findings = _findings_block(result)
    if findings:
        blocks.append(findings)

    if not result.balanced:
        blocks.append("Внимание: введённая отчётность не сходится (актив ≠ пассив) — "
                      "показатели рассчитаны по данным как есть, выводы требуют проверки "
                      "исходных данных.")

    blocks.append(_verdict(result))

    # Границы проверки идут после вердикта: они его ограничивают, а не предваряют.
    limits = _limits_block(procedures)
    if limits:
        blocks.append(limits)
    return "\n\n".join(blocks)


def opinion_is_positive(result: AuditResult) -> bool:
    """Позитивно ли заключение (для тональности UI/тестов)."""
    return result.diagnostics is not None and result.diagnostics.light == "ok"


__all__ = ["build_opinion", "opinion_is_positive", "fmt_rub"]
