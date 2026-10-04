"""Закрытие расчётов на конец горизонта (SPEC §17, пакет K, K4).

Поток проекта видит деньги только внутри горизонта, а расчёты на его конец открыты:
покупатели за последние месяцы ещё не заплатили, налог за последний год ещё не уплачен,
поставщикам ещё должны. До 0.9.57 ни одна из этих позиций в показатели не попадала —
и ошибка шла в обе стороны сразу: неуплаченный налог завышал NPV, неинкассированная
дебиторка занижала. У флагмана демо-данных на конец горизонта открыто 60 млн дебиторки и
20 млн налогов; закрыть одни налоги значило бы исправить завышение и оставить занижение.

Поэтому закрываются **все расчёты оборотного капитала** — так, как это принято в оценке
проектов («высвобождение оборотного капитала в последнем периоде»): активы расчётов
приходят деньгами, обязательства уходят. Основные средства, деньги и казначейство в
закрытие не входят: первые — вопрос оценки (Гордон, чистые активы), а не расчётов,
вторые — не поток проекта.

Закрытие — **отдельный объект**, а не молча прибавленное число: экран, печать и
документ называют его сумму и состав. Модель Гордона берёт поток без закрытия — бизнес
у неё продолжается, и капитал не высвобождается. Слой только читает баланс: отчёты и
golden-числа отчётов не меняются.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..money import ZERO, quantize
from .lines import BALANCE_LINES
from .statements import Statement

#: Что закрывается и с каким знаком: активы расчётов приходят деньгами (+),
#: обязательства уходят (−). Перечень закрыт: строка баланса вне его в закрытие не
#: входит, и это названо в примечании, а не оставлено догадке.
RELEASED: tuple[tuple[str, int], ...] = (
    ("B2", 1),    # дебиторка
    ("B3", 1),    # сырьё и материалы
    ("B4", 1),    # незавершённое производство
    ("B5", 1),    # готовая продукция
    ("B7", 1),    # предоплаты и НДС к получению (зачёт, возмещение)
    ("B21", -1),  # налоги и взносы к уплате
    ("B23", -1),  # кредиторка
    ("B24", -1),  # полученные авансы
)

_LABELS = dict(BALANCE_LINES)

_NOT_INCLUDED = ("Основные средства в закрытие не входят: их стоимость — вопрос оценки, а "
                 "не расчётов.")


@dataclass
class ReleaseItem:
    code: str
    label: str
    #: Со знаком: «+» приходит деньгами, «−» уходит.
    amount: Decimal


@dataclass
class WorkingCapitalRelease:
    """Расчёты, открытые на последний месяц горизонта, и как они вошли в показатели."""

    #: Входит ли закрытие в поток показателей (``settings.release_working_capital``).
    enabled: bool
    #: Месяц, в который закрытие отнесено, — последний месяц горизонта.
    month: int
    total: Decimal
    items: list[ReleaseItem] = field(default_factory=list)
    #: Одна строка с сервера на экран, печать и документ: второй её копии нет.
    note: str = ""


def _signed(value: Decimal) -> str:
    # Ленивый импорт: пакет ревью при загрузке тянет движок (Монте-Карло), а движок —
    # этот модуль. Форматтер рублей один на ядро — второй его копии здесь нет.
    from ..review.text import fmt_rub
    return ("+" if value > 0 else "") + fmt_rub(value)


def _note(items: list[ReleaseItem], total: Decimal, enabled: bool) -> str:
    if not items:
        return ("Расчётов, открытых на конец горизонта, нет: дебиторки, запасов, налогов и "
                "кредиторки на последний месяц не остаётся, и закрывать нечего.")
    if enabled:
        return ("Показатели эффективности считаются с закрытием расчётов на конец горизонта: "
                f"в последнем месяце поток проекта получает {_signed(total)} ₽ — открытые "
                "на этот месяц дебиторка, запасы и НДС к получению приходят деньгами, а "
                "налоги, кредиторка и полученные авансы уходят. " + _NOT_INCLUDED)
    return ("Закрытие расчётов на конец горизонта выключено: открытые на последний месяц "
            f"расчёты ({_signed(total)} ₽ — дебиторка, налоги, кредиторка) в поток "
            "проекта не входят, и показатели эффективности их не видят.")


def working_capital_release(balance: Statement, n: int, *,
                            enabled: bool) -> WorkingCapitalRelease | None:
    """Собрать закрытие расчётов по балансу последнего месяца. ``None`` — горизонта нет.

    Выключенное закрытие тоже собирается: оно называет, **что** осталось за горизонтом и
    в показатели не вошло, — молчание читалось бы как «расчётов нет».
    """
    if n <= 0:
        return None
    items: list[ReleaseItem] = []
    for code, sign in RELEASED:
        amount = balance[code][n - 1] * sign
        if quantize(amount) != ZERO:
            items.append(ReleaseItem(code=code, label=_LABELS[code], amount=amount))
    total = sum((i.amount for i in items), ZERO)
    return WorkingCapitalRelease(enabled=enabled, month=n - 1, total=total, items=items,
                                 note=_note(items, total, enabled))


def combine_releases(
        parts: list[tuple[str, WorkingCapitalRelease | None]]) -> WorkingCapitalRelease | None:
    """Закрытие расчётов группы (свод холдинга): сумма закрытий проектов по строкам.

    Поток группы — сумма потоков проектов, поэтому в закрытие группы входят только те
    проекты, у которых оно включено; остальные **названы** в оговорке, а не растворены в
    сумме. ``parts`` — пары (имя проекта, его закрытие); горизонт у проектов свода один.
    """
    present = [(name, r) for name, r in parts if r is not None]
    if not present:
        return None
    on = [r for _, r in present if r.enabled]
    off = [name for name, r in present if not r.enabled]
    by_code: dict[str, Decimal] = {}
    for r in on:
        for item in r.items:
            by_code[item.code] = by_code.get(item.code, ZERO) + item.amount
    items = [ReleaseItem(code=code, label=_LABELS[code], amount=by_code[code])
             for code, _ in RELEASED
             if code in by_code and quantize(by_code[code]) != ZERO]
    total = sum((i.amount for i in items), ZERO)
    note = _note(items, total, bool(on))
    if on and off:
        note += (" У проектов " + ", ".join(f"«{name}»" for name in off) + " закрытие "
                 "выключено — их расчёты конца горизонта в свод не входят.")
    return WorkingCapitalRelease(enabled=bool(on), month=present[0][1].month, total=total,
                                 items=items, note=note)


def with_release(flow: list[Decimal],
                 release: WorkingCapitalRelease | None) -> list[Decimal]:
    """Поток для показателей: закрытие — в последнем месяце, если оно включено."""
    out = list(flow)
    if release is not None and release.enabled and out:
        out[release.month] += release.total
    return out
