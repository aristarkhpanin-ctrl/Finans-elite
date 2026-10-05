"""Взгляд банка: покрытие долга и долговая нагрузка (SPEC §17, пакет L, L1).

Первый вопрос кредитора — покрывает ли денежный поток платежи по долгу. Покрытие
процентов прибылью в продукте было (коэффициенты, правило ревью), но проценты — только
часть платежа: тело займа платится теми же деньгами, и банк смотрит на **DSCR** —
поток, доступный для обслуживания долга, к процентам и телу вместе. Без него тот, кто шёл
с планом в банк или фонд, узнавал об отказе от банка, а не от продукта.

Правила расчёта — в одном месте, и каждое названо в оговорке, которая едет с числами:

- **Поток для обслуживания долга (CFADS)** — операционный поток ``C13`` без казначейства
  (размещение в депозиты и ценные бумаги — решение о свободных деньгах, K3) и за вычетом
  операционной части лизинга: аренда и страхование стоят в ``C25`` финансовой
  деятельности, а по смыслу это издержки.
- **Обслуживание долга** — проценты ``C24``, плановое погашение тела займов (тот же
  график, что у конвейера) и платежи финансового лизинга. **Погашение автокредита не
  входит**: это возврат из свободных денег, а не плановый платёж; его проценты входят.
- **По годам проекта** — 12 месяцев от старта, как свёртка отчётов и документ.
- Пороги — **практика банков, а не норма закона**: условия конкретного банка бывают
  строже, и это напечатано.

Слой только читает отчёты и модель: строки отчётов и показатели эффективности от него не
меняются.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..money import ZERO, quantize
from .statements import Statement

#: Месяцев в году проекта — как у свёртки отчётов и DOCX («Год 1», «Год 2» …).
YEAR = 12

#: Обычное требование банков к покрытию долга (DSCR) — практика, а не норма закона.
BANK_DSCR_MIN = Decimal("1.2")

#: Обычный предел долговой нагрузки банков: чистый долг не выше стольких годовых EBITDA.
BANK_LEVERAGE_MAX = Decimal("4")


@dataclass
class DebtYear:
    """Год проекта глазами кредитора."""

    label: str
    #: Первый месяц года (с нуля) и его длина: последний год бывает неполным.
    start: int
    months: int
    #: Поток, доступный для обслуживания долга.
    cfads: Decimal
    interest: Decimal
    #: Плановое погашение тела займов (без автокредита).
    principal: Decimal
    #: Платежи финансового лизинга.
    lease: Decimal
    #: Обслуживание долга = проценты + тело + лизинг.
    service: Decimal
    #: CFADS / обслуживание; ``None`` — платежей по долгу в этом году нет.
    dscr: Decimal | None
    #: Сколько платежей пришлось платить из других денег (при DSCR < 1), иначе ноль.
    shortfall: Decimal
    #: Чистый долг на конец года: займы и лизинг за вычетом денег и депозитов.
    net_debt: Decimal
    ebitda: Decimal
    #: Чистый долг / EBITDA; ``None`` — не считается, причина в ``leverage_note``.
    leverage: Decimal | None
    leverage_note: str = ""


@dataclass
class DebtService:
    """Покрытие долга и долговая нагрузка по годам проекта."""

    years: list[DebtYear] = field(default_factory=list)
    #: Наименьший DSCR среди лет с платежами по долгу и год, где он достигается.
    min_dscr: Decimal | None = None
    min_dscr_year: str | None = None
    #: Одна строка с сервера на экран и в документ: как считается и чего не видно.
    note: str = ""


def _year_chunks(n: int) -> list[tuple[int, int]]:
    return [(a, min(a + YEAR, n)) for a in range(0, n, YEAR)]


def _sum(series: list[Decimal], a: int, b: int) -> Decimal:
    return sum(series[a:b], ZERO)


def _fmt_share(value: Decimal) -> str:
    """«1,2» — порог словами отчёта, без хвоста нулей."""
    text = format(value.normalize(), "f")
    return text.replace(".", ",")


def _leverage(net_debt: Decimal, ebitda: Decimal, months: int) -> tuple[Decimal | None, str]:
    """Чистый долг / EBITDA и почему не считается: пустая клетка без причины читалась бы
    как «нагрузки нет»."""
    if months < YEAR:
        return None, "неполный год: годовой EBITDA нет"
    if quantize(net_debt) <= ZERO:
        return None, "чистого долга нет"
    if ebitda <= ZERO:
        return None, "EBITDA не положительна — отношение не имеет смысла"
    return net_debt / ebitda, ""


def _note(capex_years: list[str], autocredit: bool) -> str:
    parts = [
        "Покрытие долга (DSCR) — поток, доступный для обслуживания долга, к платежам по "
        "нему, по годам проекта. Поток — операционный (C13) без размещения в депозиты и "
        "ценные бумаги и за вычетом аренды по операционному лизингу и страхования; "
        "платежи — проценты, плановое погашение займов и платежи финансового лизинга. "
        "Чистый долг — займы и лизинг за вычетом денег и депозитов на конец года; "
        "EBITDA — прибыль до налога, процентов и амортизации.",
    ]
    if autocredit:
        parts.append("Погашение автокредита в платежи не входит: это возврат из свободных "
                     "денег, а не плановый платёж; его проценты входят.")
    if capex_years:
        parts.append("Капитальные вложения из потока не вычитаются: продукт не отличает "
                     "поддерживающие вложения от инвестиционных. В годы с платежами по "
                     f"долгу вложения есть ({', '.join(capex_years)}) — банк, который "
                     "вычтет поддерживающие, увидит покрытие ниже.")
    parts.append(f"Банки обычно требуют DSCR не ниже {_fmt_share(BANK_DSCR_MIN)} и чистый "
                 f"долг не выше {_fmt_share(BANK_LEVERAGE_MAX)} годовых EBITDA — это "
                 "практика, а не норма закона; условия конкретного банка бывают строже.")
    return " ".join(parts)


def compute_debt_service(income: Statement, cashflow: Statement, balance: Statement, n: int,
                         *, scheduled_principal: list[Decimal],
                         finance_lease: list[Decimal]) -> DebtService | None:
    """Собрать покрытие долга по готовым отчётам. ``None`` — долга за горизонт нет.

    ``scheduled_principal`` — плановое погашение займов (``C23`` без автокредита),
    ``finance_lease`` — платежи финансового лизинга (часть ``C25``); оба — из конвейера.
    """
    c13, c8, c9 = cashflow["C13"], cashflow["C8"], cashflow["C9"]
    c14, c23, c24, c25 = cashflow["C14"], cashflow["C23"], cashflow["C24"], cashflow["C25"]
    debt_lines = [balance["B22"][t] + balance["B26"][t] for t in range(n)]
    has_debt = (any(quantize(v) != ZERO for v in c24) or
                any(quantize(v) != ZERO for v in scheduled_principal) or
                any(quantize(v) != ZERO for v in finance_lease) or
                any(quantize(v) != ZERO for v in debt_lines))
    if n <= 0 or not has_debt:
        return None

    years: list[DebtYear] = []
    capex_years: list[str] = []
    for i, (a, b) in enumerate(_year_chunks(n)):
        label = f"Год {i + 1}"
        lease_operating = _sum(c25, a, b) - _sum(finance_lease, a, b)
        cfads = (_sum(c13, a, b) + _sum(c8, a, b) - _sum(c9, a, b) - lease_operating)
        interest = _sum(c24, a, b)
        principal = _sum(scheduled_principal, a, b)
        lease = _sum(finance_lease, a, b)
        service = interest + principal + lease
        has_service = quantize(service) > ZERO
        dscr = cfads / service if has_service else None
        shortfall = service - cfads if dscr is not None and dscr < 1 else ZERO
        end = b - 1
        net_debt = (balance["B22"][end] + balance["B26"][end]
                    - balance["B1"][end] - balance["B6"][end])
        ebitda = (_sum(income["I23"], a, b) + _sum(income["I18"], a, b)
                  + _sum(income["I17"], a, b))
        leverage, why = _leverage(net_debt, ebitda, b - a)
        if has_service and quantize(_sum(c14, a, b)) > ZERO:
            capex_years.append(label)
        years.append(DebtYear(
            label=label, start=a, months=b - a, cfads=cfads, interest=interest,
            principal=principal, lease=lease, service=service, dscr=dscr,
            shortfall=shortfall, net_debt=net_debt, ebitda=ebitda, leverage=leverage,
            leverage_note=why))

    covered = [(y.dscr, y.label) for y in years if y.dscr is not None]
    worst = min(covered, key=lambda pair: pair[0]) if covered else None
    autocredit = any(quantize(c23[t] - scheduled_principal[t]) != ZERO for t in range(n))
    return DebtService(
        years=years,
        min_dscr=worst[0] if worst else None,
        min_dscr_year=worst[1] if worst else None,
        note=_note(capex_years, autocredit),
    )
