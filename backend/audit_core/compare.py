"""Сравнение дел (Финанс-Аудит, «Экран 20»; методика — SPEC, Приложение С).

Покупатель смотрит не одну цель, а несколько, и выбирает. Модуль ставит дела рядом и
**ничего не считает**: каждое число уже посчитано в своём деле — здесь оно только
выстраивается в столбцы.

Три решения задают модуль.

**«Кто лучше» — только там, где «лучше» определено.** У Enterprise Value и цены за
100% доли направления нет: больше — это размер, а не качество сделки. У оценённого
влияния флагов его тоже нет: абсолютная сумма несопоставима между бизнесами разного
размера. Победитель выводится, лишь когда значение есть **у всех** дел.

**Сводного балла с весами нет.** Балл прячет веса за собой: два дела с разными весами
получают разные баллы при тех же числах. Вместо него — счёт побед по видимым строкам.

**Рекомендации по сделке нет.** Выбор зависит от стратегии покупателя, портфеля и
доступного финансирования — ничего этого в деле нет. Платформа, рекомендующая сделку,
притворяется инвестором.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .analysis import analyze
from .earnings import EarningsQuality, normalize_earnings
from .flags import detect_flags
from .input_check import check_input
from .models import AuditSubjectModel
from .obligations import build_obligations
from .procedures import ProcedureReport, run_procedures
from .summary import CaseSummary, build_summary
from .valuation import Valuation, build_valuation

D = Decimal

#: Ранг буквы качества прибыли: шкала объявленная (Прил. К.3), но упорядоченная.
GRADE_RANK = {"A": D(1), "B": D(2), "C": D(3)}

NOT_COMPUTED = [
    "Сводный балл с весами — веса назначает человек, а балл прячет их за собой: два дела "
    "с разными весами получают разные баллы при тех же числах. Вместо балла — счёт побед "
    "по видимым строкам.",
    "Рекомендация по сделке — выбор зависит от стратегии покупателя, его портфеля, "
    "доступного финансирования и аппетита к риску; ничего этого в деле нет.",
    "Сравнение с отраслевыми медианами — базы отраслевых мультипликаторов у платформы "
    "нет, и «выше рынка» было бы сказано наугад.",
]


@dataclass
class CaseColumn:
    """Столбец сравнения: дело и его сводные признаки."""

    subject_id: str
    name: str
    industry: str = ""
    currency: str = ""
    reporting_standard: str = ""
    last_period: str = ""
    n_periods: int = 0
    verdict: str = ""
    base_code: str = ""


@dataclass
class CompareRow:
    """Строка сравнения: показатель по всем делам и победитель, если он определён.

    ``winner`` — индекс дела; ``None`` значит одно из двух: направления у показателя нет
    (больше не значит лучше) либо значение есть не у всех. Оба случая объяснены в ``note``.
    """

    key: str
    label: str
    unit: str                          # money | ratio | percent | count | text
    direction: Optional[str] = None    # higher | lower | None — «лучше» не определено
    values: list[Optional[Decimal]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    winner: Optional[int] = None
    note: str = ""


@dataclass
class Comparison:
    """Сравнение дел: столбцы, строки, счёт побед и оговорки сопоставимости."""

    cases: list[CaseColumn] = field(default_factory=list)
    rows: list[CompareRow] = field(default_factory=list)
    #: Побед у каждого дела и число строк, по которым победитель вообще определялся.
    wins: list[int] = field(default_factory=list)
    comparable: int = 0
    caveats: list[str] = field(default_factory=list)
    #: Дела, выбывшие из сравнения (нет отчётности) — названы, а не выпали молча (С.5).
    excluded: list[str] = field(default_factory=list)
    not_computed: list[str] = field(default_factory=list)


def _metric(summary: CaseSummary, key: str) -> Optional[Decimal]:
    for m in summary.metrics:
        if m.key == key:
            return m.value
    return None


def _grade(summary: CaseSummary) -> str:
    for m in summary.metrics:
        if m.key == "grade":
            return m.text
    return "—"


@dataclass
class _Case:
    """Всё посчитанное по одному делу — вход для построения столбца."""

    subject_id: str
    model: AuditSubjectModel
    summary: CaseSummary
    valuation: Valuation
    procedures: ProcedureReport
    earnings: EarningsQuality


def _prepare(subject_id: str, model: AuditSubjectModel) -> Optional[_Case]:
    """Посчитать дело целиком; ``None`` — отчётности нет, сравнивать нечего (С.5)."""
    result = analyze(model)
    if result.n == 0:
        return None
    obligations = build_obligations(model, result)
    flags = detect_flags(model, result, obligations)
    issues = check_input(model)
    earnings = normalize_earnings(model, result)
    procedures = run_procedures(model, result, flags, issues, obligations, earnings)
    valuation = build_valuation(model, result, earnings, obligations)
    summary = build_summary(model, result, flags, issues, obligations, earnings,
                            procedures, valuation)
    return _Case(subject_id=subject_id, model=model, summary=summary,
                 valuation=valuation, procedures=procedures, earnings=earnings)


def _rows(cases: list[_Case], money_comparable: bool) -> list[CompareRow]:
    """Строки сравнения. ``money_comparable=False`` снимает победителей у денег (С.4)."""
    money_note = ("" if money_comparable
                  else "валюты дел различаются — денежные величины несопоставимы")
    base_codes = {c.earnings.base_code for c in cases}
    same_base = len(base_codes) == 1
    base_note = ("" if same_base
                 else "показатели нормализации различаются (EBIT против EBITDA) — "
                      "база расходится на всю амортизацию")

    def money(key, label, values, direction=None, note=""):
        return CompareRow(key=key, label=label, unit="money",
                          direction=direction if money_comparable else None,
                          values=values, note=note or money_note)

    rows = [
        money("revenue", "Выручка последнего периода",
              [_metric(c.summary, "revenue") for c in cases], "higher"),
        money("earnings", "Показатель прибыли нормализованный",
              [_metric(c.summary, "earnings") for c in cases],
              "higher" if same_base else None, base_note),
        CompareRow(key="leverage", label="Долг / показатель прибыли", unit="ratio",
                   direction="lower" if same_base else None,
                   values=[_metric(c.summary, "leverage") for c in cases],
                   note=base_note),
        CompareRow(key="grade", label="Качество прибыли", unit="text", direction="lower",
                   values=[GRADE_RANK.get(_grade(c.summary)) for c in cases],
                   texts=[_grade(c.summary) for c in cases],
                   note="шкала A/B/C — объявленное соглашение, а не измерение"),
        CompareRow(key="coverage", label="Охват проверки", unit="percent",
                   direction="higher",
                   values=[c.procedures.coverage for c in cases]),
        CompareRow(key="risk_flags", label="Тяжёлых флагов", unit="count",
                   direction="lower",
                   values=[D(c.summary.risk_flags) for c in cases]),
        # Абсолютная сумма несопоставима между бизнесами разного размера (С.1).
        money("priced_total", "Оценённое влияние флагов",
              [c.summary.priced_total for c in cases], None,
              "абсолютная сумма несопоставима между бизнесами разного размера — "
              "сравнимо число тяжёлых флагов выше"),
        # Размер, а не качество сделки: победителя здесь нет по определению (С.1).
        money("enterprise_value", "Enterprise Value",
              [c.valuation.enterprise_value for c in cases], None,
              "размер, а не качество сделки — «лучше» здесь не определено"),
        money("equity_value", "Цена за 100% доли",
              [c.valuation.equity_value for c in cases], None,
              "размер, а не качество сделки — «лучше» здесь не определено"),
        CompareRow(key="multiple", label="Мультипликатор EV / показатель", unit="ratio",
                   direction="lower" if same_base else None,
                   values=[c.valuation.implied_multiple for c in cases],
                   note=base_note or "медиана своя в каждой отрасли — "
                                     "сравнивайте только сопоставимые бизнесы"),
        CompareRow(key="discount", label="Дисконт к запрошенной цене", unit="percent",
                   direction="higher",
                   values=[c.valuation.discount for c in cases],
                   note="больше — выгоднее покупателю"),
    ]

    for row in rows:
        if row.direction is None:
            continue
        # Победитель только когда значение есть у всех: сравнивать посчитанное с
        # непосчитанным нельзя (С.1).
        if any(v is None for v in row.values):
            row.winner = None
            if not row.note:
                row.note = "значение есть не у всех дел — победитель не определяется"
            continue
        best = (max(row.values) if row.direction == "higher" else min(row.values))
        # Ничья победителя не даёт: «лучше» требует различия.
        if sum(1 for v in row.values if v == best) == 1:
            row.winner = row.values.index(best)
    return rows


def _caveats(cases: list[_Case], money_comparable: bool) -> list[str]:
    out: list[str] = []
    if not money_comparable:
        out.append(
            "Валюты дел различаются ("
            + ", ".join(sorted({c.model.currency for c in cases}))
            + "): денежные показатели сравнивать нельзя, победитель у них не выводится.")
    if len({c.model.industry for c in cases if c.model.industry}) > 1:
        out.append(
            "Отрасли различаются: медиана мультипликатора своя в каждой, поэтому "
            "«дешевле по EV/EBITDA» между отраслями не значит «дешевле».")
    if len({c.model.reporting_standard for c in cases}) > 1:
        out.append(
            "Основы отчётности различаются: статьи сформированы по разным правилам, "
            "и одинаково названные строки означают разное.")
    if len({c.earnings.base_code for c in cases}) > 1:
        out.append(
            "Показатели нормализации различаются (EBIT против EBITDA): база расходится "
            "на всю амортизацию, кратности и мультипликаторы несопоставимы.")
    periods = {c.model.periods[-1].label for c in cases if c.model.periods}
    if len(periods) > 1:
        out.append("Последние периоды различаются (" + ", ".join(sorted(periods))
                   + "): числа относятся к разным датам.")
    coverages = [c.procedures.coverage for c in cases]
    if any(v is not None for v in coverages) and len(set(coverages)) > 1:
        worst = min((c for c in cases if c.procedures.coverage is not None),
                    key=lambda c: c.procedures.coverage)
        out.append(
            f"Охват проверки различается: у дела «{worst.model.name or worst.subject_id}» "
            f"он ниже прочих ({worst.procedures.coverage * 100:.0f}%) — его риски могут "
            "оказаться выше показанных.")
    return out


def compare_subjects(subjects: list[tuple[str, AuditSubjectModel]]) -> Comparison:
    """Сравнить дела по уже посчитанным в каждом величинам.

    Дело без отчётности в сравнение не идёт и называется в ``excluded``: сравнивать у
    него нечего, но выпасть молча оно не может (С.5).
    """
    comparison = Comparison(not_computed=list(NOT_COMPUTED))
    cases: list[_Case] = []
    for subject_id, model in subjects:
        case = _prepare(subject_id, model)
        if case is None:
            comparison.excluded.append(model.name or subject_id)
            continue
        cases.append(case)

    if comparison.excluded:
        comparison.caveats.append(
            "В сравнение не вошли дела без введённой отчётности: "
            + ", ".join(comparison.excluded) + ".")
    if len(cases) < 2:
        comparison.caveats.append(
            "Для сравнения нужно хотя бы два дела с отчётностью.")
        return comparison

    comparison.cases = [CaseColumn(
        subject_id=c.subject_id, name=c.model.name or c.subject_id,
        industry=c.model.industry, currency=c.model.currency,
        reporting_standard=c.model.reporting_standard,
        last_period=c.model.periods[-1].label if c.model.periods else "",
        n_periods=c.model.n, verdict=c.summary.verdict,
        base_code=c.earnings.base_code) for c in cases]

    money_comparable = len({c.model.currency for c in cases}) == 1
    comparison.rows = _rows(cases, money_comparable)
    comparison.caveats.extend(_caveats(cases, money_comparable))

    comparison.wins = [sum(1 for r in comparison.rows if r.winner == i)
                       for i in range(len(cases))]
    comparison.comparable = sum(1 for r in comparison.rows if r.winner is not None)
    return comparison
