"""Консолидация отчётности группы предприятий (Финанс-Аудит, фаза H).

Свод: отчётность нескольких субъектов складывается построчно по **совпадающим периодам**,
после чего к своду применяется обычный анализ (`analyze`) — коэффициенты, тренды,
диагностика и заключение считаются для группы как для одного предприятия.

**Исключение внутригрупповых оборотов (v2).** По умолчанию свод — арифметическая сумма,
и он честно предупреждает, что внутренние операции не вычтены. Если пользователь вводит
величины внутригрупповых оборотов (``Elimination``), они **вычитаются из свода**: взаимная
задолженность, взаимная выручка, вложения участников в капитал друг друга (доли участия)
и нереализованная прибыль в запасах. Каждое исключение — **пара равных сумм по обе стороны
баланса**, поэтому равенство «актив = пассив» сохраняется (проверяется тестом).

Что **по-прежнему не делается**: гудвилл и неконтролирующая доля не выделяются отдельными
статьями — в аналитической форме их нет, а «досочинять» строки баланса нельзя. Вложения
вычитаются по балансовой стоимости, и при доле участия менее 100% капитал группы показан
по стоимости вложения, а не по чистым активам дочерних компаний; оговорка об этом
выводится вместе со сводом.

Сопоставление периодов — **по подписи** (например «2024»). Период попадает в свод, только
если он есть у **всех** участников: иначе сумма занижала бы группу по этому периоду.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from .lines import ASSET_CODES, EQLIAB_CODES, INCOME_CODES, MEMO_SUM_CODES
from .models import AuditPeriod, AuditSubjectModel
from .revaluation import apply_revaluations

#: Подписи основ отчётности для оговорок свода.
_STANDARD_LABELS = {"rsbu": "РСБУ", "ifrs": "МСФО", "management": "управленческая"}


@dataclass
class Elimination:
    """Внутригрупповые обороты к исключению (по периодам, в порядке периодов свода).

    Все величины неотрицательны и вычитаются из свода **парно**, чтобы равенство
    «актив = пассив» сохранялось:

    - ``receivables`` — взаимная задолженность: из дебиторки и из кредиторки;
    - ``revenue`` — взаимная выручка: из выручки и из себестоимости покупателя;
    - ``investments`` — вложения участников в капитал друг друга (доли участия): из
      внеоборотных активов владельца и из капитала;
    - ``unrealized_profit`` — нереализованная прибыль в запасах (наценка по внутренней
      продаже, осевшая в запасах покупателя): из запасов и из капитала, одновременно
      восстанавливая себестоимость в ОПУ — группа эту прибыль вовне не заработала.
    """

    receivables: list[Decimal] = field(default_factory=list)
    revenue: list[Decimal] = field(default_factory=list)
    investments: list[Decimal] = field(default_factory=list)
    unrealized_profit: list[Decimal] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Ни одна величина не задана (нечего исключать)."""
        return not any(v for row in (self.receivables, self.revenue, self.investments,
                                     self.unrealized_profit) for v in row)


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
                         name: str = "Группа предприятий",
                         elimination: Elimination | None = None) -> Consolidation:
    """Свести отчётность участников группы в одну модель.

    ``members`` — пары (имя субъекта, модель). Складываются все строки баланса (включая
    справочные) и ОПУ по совпадающим периодам; тип периода берётся у первого участника.
    ``elimination`` — внутригрупповые обороты, вычитаемые из свода (v2).
    """
    if not members:
        raise ValueError("Для консолидации нужен хотя бы один субъект")

    # Переоценки участников применяются до свода: иначе группа считалась бы по учётным
    # данным, а участники поодиночке — по скорректированным, и числа бы не сходились.
    revalued = [apply_revaluations(m) for _, m in members]
    models = [m for m, _ in revalued]
    revaluation_notes = [note for _, notes in revalued for note in notes]
    labels = _common_periods(models)

    skipped: dict[str, list[str]] = {}
    for subject_name, model in members:
        extra = [p.label or "(без подписи)" for p in model.periods if p.label not in labels]
        if extra:
            skipped[subject_name] = extra

    has_elim = elimination is not None and not elimination.is_empty()
    if has_elim:
        assert elimination is not None
        kinds = [what for row, what in (
            (elimination.receivables, "взаимная задолженность"),
            (elimination.revenue, "взаимная выручка"),
            (elimination.investments, "вложения в капитал участников"),
            (elimination.unrealized_profit, "нереализованная прибыль в запасах"),
        ) if any(v for v in row)]
        warnings: list[str] = [
            "Из свода исключены заданные внутригрупповые величины: " + ", ".join(kinds) + ".",
        ]
        if any(v for v in elimination.investments):
            # Разница между вложением и приходящейся на него долей чистых активов — гудвилл
            # и неконтролирующая доля. Отдельных статей под них в аналитической форме нет,
            # поэтому вычитается ровно вложение, а о недосказанном сообщаем прямо.
            warnings.append(
                "Вложения в капитал вычтены по балансовой стоимости. Гудвилл и "
                "неконтролирующая доля отдельно не выделяются — в аналитической форме нет "
                "таких статей; при доле участия менее 100% капитал группы показан по "
                "стоимости вложения, а не по чистым активам дочерних компаний.")
    else:
        warnings = [
            "Свод не исключает внутригрупповые обороты (взаимные расчёты, взаимную выручку, "
            "вложения в капитал, нереализованную прибыль в запасах) — показатели группы "
            "завышены на величину внутренних операций. Их можно задать явно, тогда они "
            "будут вычтены.",
        ]
    standards = {m.reporting_standard for m in models}
    if len(standards) > 1:
        named = ", ".join(_STANDARD_LABELS.get(s, s) for s in sorted(standards))
        warnings.append(
            f"Участники отчитываются по разным основам ({named}) — статьи свода "
            "сформированы по разным правилам и строго не сопоставимы. Платформа не "
            "трансформирует отчётность из одной основы в другую; свод сложен как есть.")
    if revaluation_notes:
        warnings.append("В свод вошли переоценённые данные участников — "
                        "числа группы отличаются от их учётной отчётности.")
        warnings += revaluation_notes
    if any(m.has_balance_row("M_MARKET_CAP") for m in models):
        warnings.append(
            "Рыночная капитализация участников в свод не перенесена: капитализация "
            "материнской компании уже включает стоимость дочерних, и сумма по группе была "
            "бы двойным счётом. Классическая модель Альтмана для группы не рассчитывается.")
    if not labels:
        warnings.append("У участников нет ни одного общего отчётного периода — свод пуст.")
    if skipped:
        details = "; ".join(f"{k}: {', '.join(v)}" for k, v in skipped.items())
        warnings.append("В свод не вошли периоды, которые есть не у всех участников "
                        f"({details}).")

    # Тип периода — из первого участника, у которого он есть (год/квартал/месяц).
    kind_of: dict[str, Literal["year", "quarter", "month"]] = {}
    for model in models:
        for p in model.periods:
            kind_of.setdefault(p.label, p.kind)

    balance: dict[str, list[Decimal]] = {}
    income: dict[str, list[Decimal]] = {}
    for code in ASSET_CODES + EQLIAB_CODES:
        balance[code] = _sum_line(models, labels, code, "balance")
    # Складываются только аддитивные справочные строки: рыночная капитализация в свод не
    # переносится (сумма капитализаций группы — двойной счёт, см. MEMO_SUM_CODES).
    # Строка переносится, **только если её кто-то ввёл**: иначе в своде появился бы ноль
    # там, где у самих участников значилось «не введено», и диагностика посчитала бы
    # модели, которые по одиночным субъектам честно оставались нерассчитанными.
    for code in MEMO_SUM_CODES:
        if any(m.has_balance_row(code) for m in models):
            balance[code] = _sum_line(models, labels, code, "balance")
    for code in INCOME_CODES:
        income[code] = _sum_line(models, labels, code, "income")

    if elimination is not None:
        _eliminate(balance, income, elimination, len(labels), warnings)

    model = AuditSubjectModel(
        name=name,
        currency=models[0].currency,
        industry="Консолидированная группа",
        # Основа свода — общая, только если она общая у участников; иначе смешение
        # уже названо в оговорке, и приписывать группе чужой стандарт нельзя.
        reporting_standard=(models[0].reporting_standard if len(standards) == 1 else "management"),
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


def _fit(values: list[Decimal], n: int) -> list[Decimal]:
    """Ряд исключений к числу периодов свода (недостающие — нули)."""
    out = list(values)[:n]
    while len(out) < n:
        out.append(Decimal(0))
    return out


def _eliminate(balance: dict[str, list[Decimal]], income: dict[str, list[Decimal]],
               elim: Elimination, n: int, warnings: list[str]) -> None:
    """Вычесть внутригрупповые обороты из свода (на месте).

    Каждое исключение — **пара** равных сумм по обе стороны баланса, иначе свод перестал
    бы сходиться (актив ≠ пассив):

    ==============================  ==================  ==================
    Что исключаем                   Актив               Пассив / ОПУ
    ==============================  ==================  ==================
    Взаимная задолженность          ``A_RECEIVABLE``    ``P_SHORT``
    Взаимная выручка                ``I_REVENUE``       ``I_COGS``
    Вложения в капитал              ``A_FIXED``         ``P_EQUITY``
    Нереализованная прибыль         ``A_INVENTORY``     ``P_EQUITY`` (+ ``I_COGS``)
    ==============================  ==================  ==================

    Сумма, превышающая свод по строке, обрезается до него с предупреждением — вычитать
    больше, чем есть, значит получить отрицательную статью и бессмысленные коэффициенты.
    """
    receivables = _fit(elim.receivables, n)
    revenue = _fit(elim.revenue, n)
    investments = _fit(elim.investments, n)
    unrealized = _fit(elim.unrealized_profit, n)

    def cap(values: list[Decimal], *rows: str, table: dict[str, list[Decimal]],
            what: str) -> list[Decimal]:
        """Обрезать вычитаемое по минимальному остатку затрагиваемых строк."""
        out: list[Decimal] = []
        for t in range(n):
            limit = min(table[row][t] for row in rows)
            wanted = values[t]
            if wanted > limit:
                warnings.append(
                    f"Исключение {what} за период {t + 1} ({wanted}) превышает свод по строке "
                    f"({limit}) — вычтено {limit}.")
                out.append(limit if limit > 0 else Decimal(0))
            else:
                out.append(wanted if wanted > 0 else Decimal(0))
        return out

    rec = cap(receivables, "A_RECEIVABLE", "P_SHORT", table=balance,
              what="взаимной задолженности")
    rev = cap(revenue, "I_REVENUE", "I_COGS", table=income, what="взаимной выручки")
    inv = cap(investments, "A_FIXED", "P_EQUITY", table=balance,
              what="вложений в капитал участников")

    for t in range(n):
        balance["A_RECEIVABLE"][t] -= rec[t]
        balance["P_SHORT"][t] -= rec[t]
        balance["A_FIXED"][t] -= inv[t]
        balance["P_EQUITY"][t] -= inv[t]
        income["I_REVENUE"][t] -= rev[t]
        income["I_COGS"][t] -= rev[t]

    # Нереализованная прибыль считается после вложений: капитал уже уменьшен на них, и
    # обрезка должна учитывать фактический остаток, а не исходный.
    unreal = cap(unrealized, "A_INVENTORY", "P_EQUITY", table=balance,
                 what="нереализованной прибыли в запасах")
    for t in range(n):
        balance["A_INVENTORY"][t] -= unreal[t]
        balance["P_EQUITY"][t] -= unreal[t]
        # Та же прибыль снимается и в ОПУ: себестоимость проданного внутри группы товара
        # восстанавливается до исходной, прибыль периода падает на ту же величину.
        income["I_COGS"][t] += unreal[t]
        # Нераспределённая прибыль — та же величина; строка справочная (в итог не входит),
        # поэтому баланс не затрагивается, но фактор моделей Альтмана остаётся согласован.
        if "M_RETAINED" in balance:
            balance["M_RETAINED"][t] -= unreal[t]
