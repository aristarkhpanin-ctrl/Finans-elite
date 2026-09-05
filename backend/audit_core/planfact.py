"""План-факт после сделки (Финанс-Аудит, «Экран 17»; методика — SPEC, Приложение Т).

Дело не заканчивается сделкой. Через год покупатель возвращается к нему с вопросом, на
который до сделки ответа не было: **сбылось ли то, что обещал продавец**, и **окупился
ли дисконт**, за который торговались.

Четыре решения задают модуль.

**План вводится, факт — уже есть.** Прогноз лежит в меморандуме, а не в отчётности;
фактические числа — это отчётность дела, и второго их источника план-факт не заводит:
иначе одно и то же дело показывало бы две разные выручки.

**Сравниваются только периоды, где план задан.** Нулевой факт при заданном плане —
полный недобор, но он же и двусмыслен: ноль значит либо «выручки не было», либо «период
ещё не отражён». Различить их платформа не может и молча не выбирает.

**Направление отклонения объявлено у каждой строки.** Выручка ниже плана — плохо,
себестоимость ниже плана — хорошо; «−12%» само по себе не значит ничего.

**Флаг «сработал» — суждение.** Предсказанное влияние посчитано платформой, фактическая
потеря вводится; обе половины подписаны.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .flags import FlagRegistry
from .lines import LABELS
from .models import AuditSubjectModel

D = Decimal

#: Порог существенности отклонения — **соглашение**, а не измерение (Т.3).
MATERIAL = D("0.10")

#: Строки план-факта и направление отклонения: больше плана — хорошо или плохо.
#: Без направления «−12%» не оценивается: у расхода минус читается как успех.
PLANFACT_LINES: list[tuple[str, str]] = [
    ("I_REVENUE", "higher"),
    ("I_COGS", "lower"),
    ("I_OPEX", "lower"),
    ("I_INTEREST", "lower"),
    ("I_TAX", "lower"),
    ("A_CASH", "higher"),
    ("A_RECEIVABLE", "lower"),
    ("A_INVENTORY", "lower"),
    ("P_LONG", "lower"),
    ("P_SHORT", "lower"),
    ("P_EQUITY", "higher"),
]


@dataclass
class PlanFactRow:
    """Строка план-факта: план, факт, отклонение и его оценка.

    ``verdict`` — ``better`` | ``worse`` | ``on_plan``: он учитывает направление, поэтому
    «себестоимость ниже плана» читается как успех, а не как недобор.
    """

    code: str
    label: str
    direction: str                     # higher | lower
    plan: Decimal = D(0)
    fact: Decimal = D(0)
    delta: Decimal = D(0)
    delta_share: Optional[Decimal] = None   # None — план нулевой, доля не считается
    verdict: str = "on_plan"
    note: str = ""


@dataclass
class RealizedFlagRow:
    """Сопоставление флага: что предсказали и во что он обошёлся фактически."""

    code: str
    title: str
    severity: str = ""
    #: Посчитано платформой (реестр флагов). ``None`` — денежной меры у флага нет.
    predicted: Optional[Decimal] = None
    realized: bool = False
    #: Введено аналитиком. ``None`` — факт ещё не оценён, а не «обошёлся в ноль».
    actual_cost: Optional[Decimal] = None
    note: str = ""


@dataclass
class PlanFact:
    """План-факт целиком: строки, охват сравнения, сопоставление флагов и оговорки."""

    available: bool = False
    #: Подписи периодов, вошедших в сравнение (Т.2) — охват виден, а не угадывается.
    periods: list[str] = field(default_factory=list)
    rows: list[PlanFactRow] = field(default_factory=list)
    flags: list[RealizedFlagRow] = field(default_factory=list)
    #: Предсказано и фактически потеряно — только по флагам с денежной мерой (Т.4).
    predicted_total: Decimal = D(0)
    realized_total: Decimal = D(0)
    #: Флаги, оценённые аналитиком, но не оценённые платформой (меры нет) — и наоборот.
    unpriced_realized: int = 0
    #: Отметки по флагам, которых в текущем реестре больше нет.
    orphan_marks: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    not_computed: list[str] = field(default_factory=list)


NOT_COMPUTED = [
    "Доходность вложения — для неё нужны цена, по которой сделка закрылась (а не "
    "запрошенная), последующие вложения, дивиденды и предположение о выходе; ничего "
    "этого в деле нет. Запрошенная цена уплаченную не заменяет: торг на то и был.",
]


def _plan_row(model: AuditSubjectModel, code: str) -> list[Decimal]:
    values = list(model.seller_plan.get(code, []))[: model.n]
    while len(values) < model.n:
        values.append(D(0))
    return values


def _fact_row(model: AuditSubjectModel, code: str) -> list[Decimal]:
    """Факт — это отчётность дела; второго источника фактических чисел здесь нет."""
    return (model.income_row(code) if code.startswith("I_")
            else model.balance_row(code))


def _fold(row: list[Decimal], covered: list[int], code: str) -> Decimal:
    """Свёртка ряда по сравниваемым периодам: поток — сумма, остаток — конец периода.

    То же правило, что в годовой свёртке отчётов первого продукта. Сложить остаток
    денежных средств за два года — получить величину, которой не существует ни в один
    момент времени.
    """
    if code.startswith("I_"):
        return sum((row[t] for t in covered), D(0))
    return row[covered[-1]]


def _verdict(direction: str, delta: Decimal, share: Optional[Decimal]) -> str:
    """Оценка отклонения с учётом направления (Т.3).

    В пределах порога существенности отклонение показывается числом, но успехом или
    провалом не объявляется: соглашение о пороге объявлено, а не подобрано.
    """
    if share is None or abs(share) < MATERIAL:
        return "on_plan"
    good = delta > 0 if direction == "higher" else delta < 0
    return "better" if good else "worse"


def build_plan_fact(model: AuditSubjectModel,
                    flags: Optional[FlagRegistry] = None) -> PlanFact:
    """План-факт по введённому прогнозу продавца и фактической отчётности дела.

    Плана нет — сравнивать не с чем: ``available=False``. Это не «всё сошлось».
    """
    result = PlanFact(not_computed=list(NOT_COMPUTED))
    if model.n == 0 or not model.seller_plan:
        result.caveats.append(
            "Прогноз продавца не введён — сравнивать факт не с чем. Внесите план из "
            "инвестиционного меморандума по тем же периодам, что и отчётность.")
        _match_flags(model, flags, result)
        return result

    # Период без плана в сравнение не идёт: у него нет второго операнда (Т.2).
    covered = [t for t in range(model.n)
               if any(_plan_row(model, code)[t] != 0 for code, _ in PLANFACT_LINES)]
    if not covered:
        result.caveats.append("Ни в одном периоде план не заполнен — сравнивать нечего.")
        _match_flags(model, flags, result)
        return result

    result.available = True
    result.periods = [model.periods[t].label or f"Период {t + 1}" for t in covered]

    ambiguous: list[str] = []
    for code, direction in PLANFACT_LINES:
        plan_row, fact_row = _plan_row(model, code), _fact_row(model, code)
        # Потоки складываются, остатки берутся на конец — то же правило, что при
        # свёртке отчётов по годам. Сложить денежные средства за два года значило бы
        # получить величину, которой не существует ни в один момент времени.
        plan = _fold(plan_row, covered, code)
        if plan == 0:
            continue                         # строка в плане не задана
        fact = _fold(fact_row, covered, code)
        delta = fact - plan
        share = delta / abs(plan)
        row = PlanFactRow(code=code, label=LABELS.get(code, code), direction=direction,
                          plan=plan, fact=fact, delta=delta, delta_share=share,
                          verdict=_verdict(direction, delta, share))
        if fact == 0:
            # Ноль значит либо «не было», либо «ещё не отражено» — платформа не
            # различает, и молча выбрать одно толкование нельзя (Т.2).
            row.note = ("факт нулевой: это либо полный недобор, либо период ещё не "
                        "отражён в отчётности — платформа их не различает")
            ambiguous.append(row.label)
        result.rows.append(row)

    if ambiguous:
        result.caveats.append(
            "Нулевой факт при заданном плане: " + ", ".join(ambiguous)
            + ". Показан как полный недобор, но может означать, что период ещё не "
              "отражён в отчётности — проверьте ввод.")
    if len(covered) < model.n:
        skipped = [model.periods[t].label or f"Период {t + 1}"
                   for t in range(model.n) if t not in covered]
        result.caveats.append(
            "Периоды без плана в сравнение не вошли: " + ", ".join(skipped) + ".")

    _match_flags(model, flags, result)
    return result


def _match_flags(model: AuditSubjectModel, flags: Optional[FlagRegistry],
                 result: PlanFact) -> None:
    """Сопоставить отметки аналитика с реестром флагов (Т.4).

    Предсказанное берётся из реестра (посчитано платформой), фактическое — из отметки
    (введено человеком). Отметка по флагу, которого в реестре больше нет, называется
    отдельно: молча выбросить её значило бы потерять работу аналитика.
    """
    registry = {f.code: f for f in (flags.flags if flags else [])}
    marks = {m.code: m for m in model.realized_flags if m.code}

    for code, flag in registry.items():
        mark = marks.get(code)
        row = RealizedFlagRow(code=code, title=flag.title, severity=flag.severity,
                              predicted=flag.impact,
                              realized=bool(mark and mark.realized),
                              actual_cost=mark.actual_cost if mark else None,
                              note=mark.note if mark else "")
        result.flags.append(row)
        if not row.realized:
            continue
        if flag.impact is None:
            # У флага нет предсказанной величины — сводить факт не с чем (то же
            # правило, что в самом реестре: мера есть не у всякого флага).
            result.unpriced_realized += 1
            continue
        result.predicted_total += flag.impact
        if row.actual_cost is not None:
            result.realized_total += row.actual_cost

    result.orphan_marks = [code for code in marks if code not in registry]
    if result.orphan_marks:
        result.caveats.append(
            "Отметки по флагам, которых в текущем реестре больше нет ("
            + ", ".join(sorted(result.orphan_marks))
            + "): данные дела правились, и правило перестало срабатывать. Отметка "
              "сохранена, но сопоставить её не с чем.")
    if result.unpriced_realized:
        result.caveats.append(
            f"Реализовавшихся флагов без денежной меры: {result.unpriced_realized}. "
            "В сопоставление они не входят — предсказанной величины у них нет вовсе.")
