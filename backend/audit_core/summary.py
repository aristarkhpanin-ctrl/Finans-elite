"""Сводка дела и вердикт (Финанс-Аудит, «Экран 1»; методика — SPEC, Приложение Н).

Первый экран дела отвечает на вопрос, ради которого дело и заведено: **что здесь видно
и чему из этого можно верить**. Модуль ничего не считает заново — собирает готовое:
светофор диагностики, реестр флагов, качество прибыли, реестр обязательств и чек-лист
процедур. Единственная новая величина — Долг / EBITDA (Н.2).

Три решения задают модуль.

**Вердикт ограничен охватом.** Ошибка ввода отменяет вердикт целиком (``unreliable``):
числа, выведенные из противоречивой отчётности, нельзя ни подтвердить, ни опровергнуть.
Хотя бы один тяжёлый флаг не даёт зелёного, каким бы ни был светофор. И рядом с
вердиктом **всегда** стоит охват: «устойчивое состояние» при охвате 60% — это оценка
шести десятых работы.

**Оценки сделки здесь нет.** Макет показывает «дисконт к цене 18%» и справедливую
стоимость. Запрошенной цены в модели не существует, DCF не построен, бенчмарков нет —
вычисленный из ничего дисконт унесли бы в переговоры. На его месте стоит оценённое
влияние флагов, и сказано, что скидкой оно не является.

**Что не посчитано — перечислено.** Отсутствующий раздел читается как благополучие,
поэтому сводка называет свои пробелы сама.

Чистые функции над готовыми результатами. **В ``AuditResult`` не входят.**
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .earnings import EarningsQuality
from .flags import FlagRegistry
from .input_check import InputIssue
from .models import AuditSubjectModel
from .obligations import ObligationRegister
from .procedures import ProcedureReport
from .result import AuditResult

D = Decimal

#: Вердикт. ``unreliable`` — данные противоречивы, вердикт не выносится вовсе.
UNRELIABLE, RISK, WARNING, OK = "unreliable", "risk", "warning", "ok"

#: Пороги тона Долг/EBITDA — **объявленное соглашение** (Н.2), а не измерение.
LEVERAGE_OK = D("2.5")
LEVERAGE_WARN = D("4.0")

_VERDICT_ORDER = {UNRELIABLE: 0, RISK: 1, WARNING: 2, OK: 3}

_HEADLINE = {
    UNRELIABLE: "Вердикт по этим данным не выносится",
    RISK: "Признаки неустойчивости",
    WARNING: "Есть зоны внимания",
    OK: "Критических отклонений не выявлено",
}


@dataclass
class HeadMetric:
    """Показатель шапки: значение, единица и тон. ``value=None`` — не считается."""

    key: str
    label: str
    value: Optional[Decimal]
    unit: str                      # money | ratio | grade
    note: str = ""
    tone: str = "neutral"          # ok | warn | risk | neutral
    #: Буквенное значение (качество прибыли) — у него нет числа.
    text: str = ""


@dataclass
class CaseSummary:
    """Сводка дела: вердикт, охват, показатели шапки и честный список пробелов."""

    #: empty — отчётность не введена; ready — сводка посчитана.
    state: str = "empty"
    verdict: str = OK
    headline: str = ""
    detail: str = ""
    #: Охват проверки и число незакрытых процедур — часть вердикта, не сноска.
    coverage: Optional[Decimal] = None
    open_procedures: int = 0
    metrics: list[HeadMetric] = field(default_factory=list)
    risk_flags: int = 0
    warning_flags: int = 0
    #: Оценённое влияние флагов. **Не скидка к цене** (Н.3).
    priced_total: Decimal = D(0)
    unpriced: int = 0
    input_errors: int = 0
    #: Что сводка намеренно не считает — перечисляется, иначе читается как благополучие.
    not_computed: list[str] = field(default_factory=list)


def _line(lines, code: str) -> list[Decimal]:
    for ln in lines:
        if ln.code == code:
            return list(ln.values)
    return []


def leverage(result: AuditResult, earnings: EarningsQuality) -> Optional[Decimal]:
    """Долг / нормализованный показатель прибыли последнего периода (Н.2).

    ``None`` при показателе ≤ 0: долг к убытку не измеряется кратностью — вышло бы
    отрицательное «плечо», которое читается как малый долг.
    """
    n = result.n
    if n == 0 or not earnings.normalized:
        return None
    base = earnings.normalized[n - 1]
    if base <= 0:
        return None
    long_, short = _line(result.balance, "P_LONG"), _line(result.balance, "P_SHORT")
    if not long_ or not short:
        return None
    return (long_[n - 1] + short[n - 1]) / base


def _leverage_tone(value: Optional[Decimal]) -> str:
    if value is None:
        return "neutral"
    if value <= LEVERAGE_OK:
        return "ok"
    return "warn" if value <= LEVERAGE_WARN else "risk"


def _metrics(result: AuditResult, earnings: EarningsQuality,
             obligations: ObligationRegister) -> list[HeadMetric]:
    n = result.n
    last = n - 1
    out: list[HeadMetric] = []

    revenue = _line(result.income, "I_REVENUE")
    out.append(HeadMetric(
        key="revenue", label=f"Выручка {result.periods[last]}" if result.periods
        else "Выручка", value=revenue[last] if revenue else None, unit="money"))

    base = earnings.base_code
    out.append(HeadMetric(
        key="earnings", label=f"{base} нормализованный",
        value=earnings.normalized[last] if earnings.normalized else None, unit="money",
        note=("корректировок нет — принят по отчётности" if not earnings.has_adjustments
              else f"после {len(earnings.adjustments)} корректировок")))

    lev = leverage(result, earnings)
    out.append(HeadMetric(
        key="leverage", label=f"Долг / {base}", value=lev, unit="ratio",
        tone=_leverage_tone(lev),
        note=("показатель прибыли не положителен — кратность не считается"
              if lev is None else "норма до 2.5×, внимание до 4.0× — соглашение методики")))

    out.append(HeadMetric(
        key="grade", label="Качество прибыли", value=None, unit="grade",
        text=earnings.grade or "—",
        tone={"A": "ok", "B": "warn", "C": "risk"}.get(earnings.grade or "", "neutral"),
        note=(earnings.grade_note if earnings.grade
              else "отчётный показатель равен нулю — сравнивать не с чем")))

    if obligations.has_rows:
        # Забалансовое показывается отдельной величиной — оно не складывается с долгом.
        out.append(HeadMetric(
            key="off_balance", label="Забалансовые обязательства",
            value=obligations.off_balance, unit="money",
            tone="warn" if obligations.off_balance > 0 else "neutral",
            note="с долгом в балансе не складывается"))
    return out


#: Чего сводка не считает — и почему. Список идёт на экран как есть (Н.3).
NOT_COMPUTED = [
    "Оценка сделки (DCF, мультипликаторы) — запрошенной цены в модели нет, "
    "модель оценки не построена.",
    "Подтверждение выручки банковской выпиской — выписок в деле нет: платформа "
    "работает с агрегатной отчётностью.",
    "Сравнение с отраслью — базы отраслевых показателей нет; сравнивать с выдуманной "
    "нормой хуже, чем не сравнивать.",
]


def build_summary(model: AuditSubjectModel, result: AuditResult,
                  flags: FlagRegistry, issues: Sequence[InputIssue] = (),
                  obligations: Optional[ObligationRegister] = None,
                  earnings: Optional[EarningsQuality] = None,
                  procedures: Optional[ProcedureReport] = None) -> CaseSummary:
    """Сводка дела по уже посчитанным результатам.

    Пустая модель даёт ``state="empty"``: без отчётности вердикта не существует —
    и «зелёного по умолчанию» тоже.
    """
    earnings = earnings if earnings is not None else EarningsQuality()
    obligations = obligations if obligations is not None else ObligationRegister()
    issues = tuple(issues)

    summary = CaseSummary(not_computed=list(NOT_COMPUTED))
    if result.n == 0:
        summary.detail = ("Отчётность не введена. Введите баланс и отчёт о финансовых "
                          "результатах хотя бы за один период — или загрузите их из "
                          "XLSX: сводка, флаги и заключение считаются по ним.")
        summary.headline = "Отчётность ещё не введена"
        return summary

    summary.state = "ready"
    summary.risk_flags = sum(1 for f in flags.flags if f.severity == "risk")
    summary.warning_flags = sum(1 for f in flags.flags if f.severity == "warning")
    summary.priced_total = flags.priced_total
    summary.unpriced = flags.unpriced
    summary.input_errors = sum(1 for i in issues if i.severity == "error")
    summary.metrics = _metrics(result, earnings, obligations)

    if procedures is not None:
        summary.coverage = procedures.coverage
        summary.open_procedures = sum(1 for i in procedures.items if i.is_open)

    light = result.diagnostics.light if result.diagnostics is not None else OK
    verdict = light if light in _VERDICT_ORDER else WARNING
    if summary.risk_flags:
        # Тяжёлый флаг перевешивает сводную оценку — как NPV < 0 в первом продукте.
        verdict = min(verdict, WARNING, key=lambda v: _VERDICT_ORDER[v])
    if summary.input_errors:
        # Противоречивая отчётность отменяет вердикт целиком, а не понижает его.
        verdict = UNRELIABLE
    summary.verdict = verdict
    summary.headline = _HEADLINE[verdict]
    summary.detail = _detail(summary)
    return summary


def _detail(s: CaseSummary) -> str:
    """Пояснение к вердикту: чем он вызван и на какой доле работы получен."""
    if s.verdict == UNRELIABLE:
        parts = [f"Проверка ввода нашла ошибок: {s.input_errors}. Пока отчётность "
                 "противоречива, показатели по ней не подтверждают и не опровергают "
                 "ничего — вердикт не выносится."]
    else:
        if s.risk_flags:
            parts = [f"Тяжёлых флагов: {s.risk_flags}. Хотя бы один такой флаг не даёт "
                     "оценить состояние как благополучное, каким бы ни был светофор."]
        elif s.warning_flags:
            parts = [f"Флагов внимания: {s.warning_flags}; тяжёлых нет."]
        else:
            parts = ["Красных флагов по введённой отчётности не найдено."]

    if s.coverage is not None:
        parts.append(f"Охват проверки — {s.coverage * 100:.0f}%, незакрытых процедур: "
                     f"{s.open_procedures}. Вердикт относится к выполненной части: "
                     "непроверенное не считается благополучным.")
    return " ".join(parts)
