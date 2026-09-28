"""Бизнес-план из дела «Финанс-Аудита» (пакет G, G14): черновик модели «Элиты».

Проверенную фирму дальше планируют — и раньше её остатки перепечатывали руками. Мост
собирает **черновик** модели: стартовый баланс — из последнего периода дела, дата
старта — после его окончания, происхождение — разделом бизнес-плана. Черновик не
сохраняется: его показывают человеку вместе с оговорками и создают проект обычным
сохранением, со всеми проверками «Элиты» (тариф, квота, журнал).

Правила:

* **Неразделимое не угадывается.** Форма дела агрегатная: «Краткосрочные обязательства»
  не делятся на займы и кредиторку — отнесены к краткосрочным займам (B22, автоматически
  не гасятся); запасы — одной строкой в сырьё; внеоборотные активы — одной строкой
  остаточной стоимости. Каждое такое отнесение **названо** — в оговорках и в разделе.
* **Переоценки дела применяются** (та же `apply_revaluations`, что у анализа) и названы:
  план начинается с оценки аналитика, а не с балансовой цифры, которую он сам поправил.
* **Несходящийся баланс — отказ, а не черновик**: стартовый баланс «Элиты» обязан
  сходиться, и модель, которая не посчитается, хуже честного отказа с разницей.
* Дата старта выводится из подписи периода, только если она читается однозначно
  («2025», «2025 Q2», «дек 2025»); иначе — не угадывается, выбирает человек.

Ядра обоих продуктов не затрагиваются: мост читает модель дела и собирает входную
модель «Элиты» — ни анализ, ни расчёт он не меняет.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from audit_core.lines import ASSET_CODES, EQLIAB_CODES
from audit_core.models import AuditSubjectModel
from audit_core.revaluation import apply_revaluations
from calc_core.models import Company, ProjectHeader, ProjectModel, StartingBalance
from calc_core.models.project import PlanSection

#: Допуск сходимости — как у проверки стартового баланса «Элиты».
_TOLERANCE = Decimal("0.01")

PROVENANCE_TITLE = "Происхождение модели"

_KIND_WORDS = {"year": "год", "quarter": "квартал", "month": "месяц"}
_STANDARD_WORDS = {"rsbu": "РСБУ", "ifrs": "МСФО", "management": "управленческая"}
#: Месяцы по началу слова; «май» — отдельно, иначе «ма» поймало бы и «март».
_MONTHS = [r"янв", r"фев", r"мар", r"апр", r"ма[йя]", r"июн", r"июл", r"авг", r"сен",
           r"окт", r"ноя", r"дек"]


class BridgeError(ValueError):
    """Черновик не собирается — причина словами, для человека."""


@dataclass
class Draft:
    model: ProjectModel
    #: Что и куда перенесено, что не перенесено и почему — показывается **до** создания.
    notes: list[str]
    period_label: str
    #: `None` — подпись периода не читается как дата, и она не угадывается.
    start_date: date | None
    revaluations: list[str] = field(default_factory=list)


def _money(x: Decimal) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",")


def _year(label: str) -> int | None:
    found = re.findall(r"(?<!\d)(\d{4})(?!\d)", label)
    return int(found[0]) if len(found) == 1 else None


def start_after(label: str, kind: str) -> date | None:
    """Первое число после окончания периода — или `None`, если подпись неоднозначна."""
    text = label.strip().lower()
    year = _year(text)
    if year is None:
        return None
    if kind == "year":
        return date(year + 1, 1, 1)
    if kind == "quarter":
        # «Q2», «кв. 2», «2 кв», «2 квартал». Цифра номера не должна быть хвостом года:
        # в «2024 q1» четвёрка перед « q» — это год, а не квартал.
        found = re.findall(r"q\s*([1-4])(?!\d)|кв\w*\.?\s*([1-4])(?!\d)"
                           r"|(?<!\d)([1-4])\s*(?:-?й\s*)?(?:q|кв)", text)
        quarters = {int(a or b or c) for a, b, c in found}
        if len(quarters) != 1:
            return None
        month = quarters.pop() * 3 + 1          # первый месяц следующего квартала
        return date(year + 1, 1, 1) if month > 12 else date(year, month, 1)
    if kind == "month":
        months = {i for i, stem in enumerate(_MONTHS, start=1) if re.search(stem, text)}
        numeric = re.findall(r"(?<!\d)(\d{1,2})[./-]\d{4}(?!\d)|(?<!\d)\d{4}[./-](\d{1,2})(?!\d)",
                             text)
        months |= {int(a or b) for a, b in numeric if 1 <= int(a or b) <= 12}
        if len(months) != 1:
            return None
        month = months.pop()
        return date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return None


#: В чём введена отчётность дела. Единицы измерения у дела нет — суммы вводятся «как
#: есть», а формы РСБУ обычно печатаются в тысячах: угадать нельзя, спрашивается человек.
UNITS: dict[int, str] = {1: "в рублях", 1000: "в тысячах рублей"}


def business_plan_draft(subject_name: str, audit: AuditSubjectModel, *,
                        default_start: date, months: int = 36, scale: int = 1) -> Draft:
    """Черновик модели «Элиты» из последнего периода дела. `BridgeError` — с причиной.

    ``scale`` — во сколько раз суммы дела меньше рублей (1 или 1000): единицы у дела нет,
    и ответ даёт человек; выбор назван первой оговоркой.
    """
    if scale not in UNITS:
        raise BridgeError("Отчётность дела — в рублях (1) или в тысячах рублей (1000).")
    if audit.n == 0:
        raise BridgeError("В деле нет периодов — переносить нечего.")
    revalued, reval_notes = apply_revaluations(audit)
    last = audit.n - 1
    period = audit.periods[last]
    label = period.label.strip() or f"период {audit.n}"

    def value(code: str) -> Decimal:
        return revalued.balance_row(code)[last] * scale

    assets = sum((value(c) for c in ASSET_CODES), Decimal(0))
    liabilities = sum((value(c) for c in EQLIAB_CODES), Decimal(0))
    if assets == 0 and liabilities == 0:
        raise BridgeError(f"В последнем периоде дела («{label}») баланс не введён — "
                          "переносить нечего.")
    if abs(assets - liabilities) > _TOLERANCE:
        raise BridgeError(
            f"В последнем периоде дела («{label}») актив ({_money(assets)}) не равен пассиву "
            f"({_money(liabilities)}), разница {_money(assets - liabilities)}. Стартовый "
            "баланс «Элиты» обязан сходиться — исправьте отчётность дела.")

    notes: list[str] = [
        f"Стартовый баланс — из последнего периода дела: «{label}» "
        f"({_KIND_WORDS.get(period.kind, period.kind)}). Суммы дела приняты "
        f"{UNITS[scale]}" + (" и умножены на 1000." if scale != 1 else "."),
        "Денежные средства → касса (B1); дебиторская задолженность → дебиторка (B2, "
        "инкассируется в первом месяце).",
        "Запасы → одной строкой в сырьё и материалы (B3): форма дела не делит их на сырьё "
        "и готовую продукцию.",
        "Внеоборотные активы → остаточная стоимость ОС одной строкой (B14): без "
        "амортизации и в базе налога на имущество, пока не детализированы активами с датой "
        "покупки до старта (вкладка «Активы»).",
        "Долгосрочные обязательства → долгосрочные займы (B26).",
        "Краткосрочные обязательства → краткосрочные займы (B22): форма дела не делит их на "
        "займы и кредиторку. Автоматически они не гасятся — погашение и кредиторку задайте "
        "сами.",
    ]

    equity = value("P_EQUITY")
    retained = paid_in = Decimal(0)
    if audit.has_balance_row("M_RETAINED"):
        retained = value("M_RETAINED")
        paid_in = equity - retained
        notes.append("Капитал: нераспределённая прибыль из справочной строки дела → B32, "
                     "остальной капитал одной строкой → уставный капитал (B27).")
    elif equity >= 0:
        paid_in = equity
        notes.append("Капитал → одной строкой в уставный капитал (B27): нераспределённая "
                     "прибыль в деле не выделена. Если она известна, перенесите её в B32.")
    else:
        retained = equity
        notes.append("Капитал отрицательный → непокрытый убыток (B32): нераспределённая "
                     "прибыль в деле не выделена, а отрицательного уставного капитала не "
                     "бывает.")

    start = start_after(period.label, period.kind)
    if start is None:
        notes.append(f"Подпись периода «{label}» не читается как дата однозначно — дата "
                     "старта не угадана, выберите её сами.")
    currency = (audit.currency or "RUB").upper()
    if currency not in ("RUB", "RUR", "₽"):
        notes.append(f"Отчётность дела — в {currency}, а расчёт «Элиты» ведётся в рублях: "
                     "суммы перенесены без пересчёта — пересчитайте их по курсу на дату "
                     "старта.")
    if reval_notes:
        notes.append("Применены переоценки дела — план начинается с оценки аналитика, а не "
                     "с балансовой цифры: " + "; ".join(reval_notes))
    notes.append("Не перенесено: выручка и расходы (отчёт дела описывает прошлое, план — "
                 "будущее: продукты, объёмы и цены вводятся заново) и реестр обязательств "
                 "дела (ставки и сроки займов — в деле, в модели их нужно задать).")

    opening = StartingBalance(
        cash=value("A_CASH"), receivables=value("A_RECEIVABLE"),
        raw_materials=value("A_INVENTORY"), fixed_assets_net=value("A_FIXED"),
        debt=value("P_LONG"), short_term_debt=value("P_SHORT"),
        paid_in_capital=paid_in, retained_earnings=retained,
    )
    standard = _STANDARD_WORDS.get(audit.reporting_standard, audit.reporting_standard)
    provenance = (
        f"Модель начата из дела «{subject_name}» продукта «Финанс-Аудит» (основа отчётности "
        f"— {standard}). " + " ".join(notes)
    )
    model = ProjectModel(
        header=ProjectHeader(name=subject_name, start_date=start or default_start,
                             duration_months=months),
        company=Company(starting_balance=opening),
        business_plan=[PlanSection(title=PROVENANCE_TITLE, text=provenance)],
    )
    return Draft(model=model, notes=notes, period_label=label, start_date=start,
                 revaluations=reval_notes)
