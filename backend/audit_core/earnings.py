"""Качество прибыли и нормализация (Финанс-Аудит; методика — SPEC, Приложение К).

Продавец показывает прибыль. Покупатель её **нормализует**: убирает разовое, возвращает
избыточное вознаграждение собственника, вычищает непрофильное — и получает то, что
бизнес зарабатывает устойчиво. Мультипликатор сделки умножается именно на этот
показатель, поэтому цена ошибки здесь равна цене ошибки в оценке.

Два решения задают весь модуль.

**EBITDA из нашей формы не выводится.** Амортизации в аналитической форме нет, поэтому
EBIT считается, а EBITDA — нет. Введена справочная строка `M_DEPRECIATION` — считаем
EBITDA; не введена — нормализуем EBIT и **называем его EBIT**. Подписать EBIT словом
EBITDA значило бы сдвинуть мультипликатор на всю амортизацию.

**Корректировки задаёт пользователь.** Что считать разовым доходом, знает проверяющий,
а не формула. Система лишь складывает поправки, перечисляет их с причинами и нигде не
выдаёт нормализованный показатель за отчётный.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .models import AuditSubjectModel
from .result import AuditResult

D = Decimal

#: Виды корректировок (SPEC, Приложение К.2) → человекочитаемая подпись.
ADJUSTMENT_KINDS: dict[str, str] = {
    "one_off": "Разовый доход или расход",
    "owner": "Вознаграждение собственника сверх рыночного",
    "related_party": "Сделка со связанной стороной не по рынку",
    "non_operating": "Непрофильная деятельность",
    "accounting": "Учётное искажение",
}

#: Границы шкалы качества — **соглашение**, а не измерение (SPEC, Приложение К.3).
GRADE_A_MAX = D("0.05")
GRADE_B_MAX = D("0.20")


@dataclass
class AppliedAdjustment:
    """Применённая поправка: что, почему и на сколько в каждом периоде."""

    label: str
    kind: str
    kind_label: str
    amounts: list[Decimal] = field(default_factory=list)
    total: Decimal = D(0)


@dataclass
class EarningsQuality:
    """Нормализация показателя прибыли по периодам.

    ``base_code`` — что именно нормализовано: ``EBITDA`` (введена амортизация) или
    ``EBIT``. Экран обязан показывать это имя: два показателя различаются на всю
    амортизацию, и мультипликатор, применённый не к тому, ошибётся ровно на неё.
    """

    base_code: str = "EBIT"
    reported: list[Decimal] = field(default_factory=list)
    normalized: list[Decimal] = field(default_factory=list)
    adjustments: list[AppliedAdjustment] = field(default_factory=list)
    #: Оценка качества по последнему периоду: A | B | C; ``None`` — сравнивать не с чем.
    grade: Optional[str] = None
    grade_note: str = ""
    #: Расхождение нормализованного с отчётным в последнем периоде (доля).
    deviation: Optional[Decimal] = None

    @property
    def has_adjustments(self) -> bool:
        return bool(self.adjustments)


def _line(lines, code: str) -> list[Decimal]:
    for ln in lines:
        if ln.code == code:
            return list(ln.values)
    return []


def _grade(reported: Decimal, normalized: Decimal) -> tuple[Optional[str], Decimal | None, str]:
    """Буква качества и расхождение по последнему периоду.

    Шкала объявлена в SPEC и здесь только применяется. Отдельный случай — уход
    нормализованного показателя в ноль или минус при положительном отчётном: это не
    «сильное расхождение», а другой факт — заявленной прибыльности нет вовсе.
    """
    if reported == 0:
        return None, None, ("Отчётный показатель равен нулю — сравнивать нормализованный "
                            "не с чем.")
    deviation = abs(normalized - reported) / abs(reported)
    if reported > 0 and normalized <= 0:
        return "C", deviation, ("После корректировок показатель уходит в ноль или минус: "
                                "заявленная прибыльность не подтверждается.")
    if deviation <= GRADE_A_MAX:
        return "A", deviation, "Отчётная прибыль подтверждается: корректировки незначительны."
    if deviation <= GRADE_B_MAX:
        return "B", deviation, "Прибыль требует оговорок: корректировки заметны."
    return "C", deviation, ("Корректировки меняют картину: отчётная прибыль расходится "
                            "с нормализованной более чем на 20%.")


def normalize_earnings(model: AuditSubjectModel, result: AuditResult) -> EarningsQuality:
    """Нормализованный показатель прибыли по периодам.

    Пустой список поправок инертен: нормализованный ряд равен отчётному, оценка — A.
    Это не «нечего показывать», а содержательный ответ: отчётность принята как есть.
    """
    n = result.n
    q = EarningsQuality()
    if n == 0:
        return q

    ebit = _line(result.income, "I_EBIT")
    if not ebit:
        return q

    # EBITDA существует только при введённой амортизации — иначе нормализуем EBIT.
    if model.has_income_row("M_DEPRECIATION"):
        depreciation = model.income_row("M_DEPRECIATION")
        q.base_code = "EBITDA"
        q.reported = [ebit[t] + depreciation[t] for t in range(n)]
    else:
        q.base_code = "EBIT"
        q.reported = list(ebit)

    total = [D(0)] * n
    for adj in model.earnings_adjustments:
        if not adj.label:
            continue                     # поправка без причины не применяется (см. К.2)
        amounts = list(adj.amounts)[:n] + [D(0)] * max(0, n - len(adj.amounts))
        q.adjustments.append(AppliedAdjustment(
            label=adj.label, kind=adj.kind,
            kind_label=ADJUSTMENT_KINDS.get(adj.kind, adj.kind),
            amounts=amounts, total=sum(amounts, D(0)),
        ))
        for t in range(n):
            total[t] += amounts[t]

    q.normalized = [q.reported[t] + total[t] for t in range(n)]
    q.grade, q.deviation, q.grade_note = _grade(q.reported[n - 1], q.normalized[n - 1])
    return q
