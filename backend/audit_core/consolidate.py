"""Консолидация отчётности группы предприятий (Финанс-Аудит, фаза H).

Свод: отчётность нескольких субъектов складывается построчно по **совпадающим периодам**,
после чего к своду применяется обычный анализ (`analyze`) — коэффициенты, тренды,
диагностика и заключение считаются для группы как для одного предприятия.

**Важное ограничение (заявляется явно).** Это **арифметический свод**, а не полная
консолидация по правилам учёта: **внутригрупповые обороты не исключаются** (взаимная
дебиторская/кредиторская задолженность, взаимная выручка, доли участия). Для исключения
нужны данные о внутригрупповых операциях, которых во вводе фактической отчётности нет.
Поэтому свод предупреждает об этом, а не создаёт видимость аудиторской консолидации.
Исключение внутригрупповых оборотов — v2 (требует ввода взаимных расчётов).

Сопоставление периодов — **по подписи** (например «2024»). Период попадает в свод, только
если он есть у **всех** участников: иначе сумма занижала бы группу по этому периоду.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from .lines import ASSET_CODES, EQLIAB_CODES, INCOME_CODES, MEMO_CODES
from .models import AuditPeriod, AuditSubjectModel


@dataclass
class Consolidation:
    """Результат свода: модель группы + что вошло и о чём предупредить."""

    model: AuditSubjectModel
    periods_used: list[str] = field(default_factory=list)
    #: Периоды участников, не вошедшие в свод (нет у всех): субъект → подписи.
    skipped: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _common_periods(models: list[AuditSubjectModel]) -> list[str]:
    """Подписи периодов, присутствующие у всех участников (в порядке первого участника)."""
    if not models:
        return []
    label_sets = [{p.label for p in m.periods if p.label} for m in models]
    common = set.intersection(*label_sets) if label_sets else set()
    seen: list[str] = []
    for p in models[0].periods:
        if p.label in common and p.label not in seen:
            seen.append(p.label)
    return seen


def consolidate_subjects(members: list[tuple[str, AuditSubjectModel]], *,
                         name: str = "Группа предприятий") -> Consolidation:
    """Свести отчётность участников группы в одну модель.

    ``members`` — пары (имя субъекта, модель). Складываются все строки баланса (включая
    справочные) и ОПУ по совпадающим периодам; тип периода берётся у первого участника.
    """
    if not members:
        raise ValueError("Для консолидации нужен хотя бы один субъект")

    models = [m for _, m in members]
    labels = _common_periods(models)

    skipped: dict[str, list[str]] = {}
    for subject_name, model in members:
        extra = [p.label or "(без подписи)" for p in model.periods if p.label not in labels]
        if extra:
            skipped[subject_name] = extra

    warnings: list[str] = [
        "Свод не исключает внутригрупповые обороты (взаимные расчёты, взаимную выручку, "
        "доли участия) — показатели группы завышены на величину внутренних операций.",
    ]
    if not labels:
        warnings.append("У участников нет ни одного общего отчётного периода — свод пуст.")
    if skipped:
        details = "; ".join(f"{k}: {', '.join(v)}" for k, v in skipped.items())
        warnings.append("В свод не вошли периоды, которые есть не у всех участников "
                        f"({details}).")

    # Тип периода — из первого участника, у которого он есть (год/квартал).
    kind_of: dict[str, Literal["year", "quarter"]] = {}
    for model in models:
        for p in model.periods:
            kind_of.setdefault(p.label, p.kind)

    balance: dict[str, list[Decimal]] = {}
    income: dict[str, list[Decimal]] = {}
    for code in ASSET_CODES + EQLIAB_CODES + MEMO_CODES:
        balance[code] = _sum_line(models, labels, code, "balance")
    for code in INCOME_CODES:
        income[code] = _sum_line(models, labels, code, "income")

    model = AuditSubjectModel(
        name=name,
        currency=models[0].currency,
        industry="Консолидированная группа",
        periods=[AuditPeriod(label=label, kind=kind_of.get(label, "year"))
                 for label in labels],
        balance=balance,
        income=income,
    )
    return Consolidation(model=model, periods_used=labels, skipped=skipped, warnings=warnings)


def _sum_line(models: list[AuditSubjectModel], labels: list[str], code: str,
              table: str) -> list[Decimal]:
    """Сумма строки по участникам для каждого общего периода (по подписи периода)."""
    out: list[Decimal] = []
    for label in labels:
        total = Decimal(0)
        for model in models:
            index = next((i for i, p in enumerate(model.periods) if p.label == label), None)
            if index is None:
                continue
            row = (model.balance_row(code) if table == "balance"
                   else model.income_row(code))
            total += row[index]
        out.append(total)
    return out
