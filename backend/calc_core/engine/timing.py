"""Временно́е распределение платежей → оборотный капитал (SPEC §5, §7).

Разрыв между начислением (accrual) и оплатой (cash) формирует:
- дебиторку (B2) — отгружено, деньги ещё не получены;
- авансы (B24) — деньги получены, отгрузка ещё не произошла;
- кредиторку (B23) — начислено, поставщику ещё не оплачено.

Конструкция сохраняет балансовый инвариант: для каждого потока выполняется тождество
``cumulative(accrual) − cumulative(cash) = (дебиторка − авансы)`` для продаж и
``= кредиторка`` для издержек (см. доказательство в комментариях к §5 спецификации).
"""
from __future__ import annotations

from decimal import Decimal

from ..series import zeros


def _payment_parts(terms) -> list[tuple[int, Decimal]]:
    """Эффективный график оплаты как список (сдвиг, доля).

    Непустой ``schedule`` заменяет простые поля; недостающая до 1 доля балансируется в
    месяце отгрузки (сдвиг 0) — сумма оплат всегда равна выручке. Пустой ``schedule`` →
    простая схема (предоплата + остаток с отсрочкой) тем же представлением.
    """
    schedule = getattr(terms, "schedule", None) or []
    if schedule:
        parts = [(p.offset_months, p.share) for p in schedule if p.share != 0]
        remainder = Decimal(1) - sum((share for _, share in parts), Decimal(0))
        if remainder != 0:
            parts.append((0, remainder))
        return parts
    parts = []
    if terms.prepayment_share != 0:
        parts.append((-terms.advance_lead_months, terms.prepayment_share))
    rest = Decimal(1) - terms.prepayment_share
    if rest != 0:
        parts.append((terms.payment_delay_months, rest))
    return parts


def sales_timing(revenue: list[Decimal], terms, n: int):
    """Распределить выручку по условиям оплаты.

    Возвращает ``(cash, receivables, advances)`` — помесячные ряды (на конец периода
    для балансовых B2/B24). Каждая доля: сдвиг < 0 — предоплата (аванс B24 до отгрузки),
    сдвиг > 0 — рассрочка (дебиторка B2 до получения денег).
    """
    cash = zeros(n)
    receivables = zeros(n)
    advances = zeros(n)
    parts = _payment_parts(terms)

    for s in range(n):
        r = revenue[s]
        if r == 0:
            continue
        for offset, share in parts:
            amt = share * r
            if amt == 0:
                continue
            if offset < 0:
                # Предоплата: приходит за |offset| мес. до поставки s; до поставки — аванс (B24).
                rp = max(0, s + offset)
                cash[rp] += amt
                for t in range(rp, s):          # аванс на конец периодов [rp, s-1]
                    advances[t] += amt
            else:
                # Оплата через offset мес. после поставки; до получения — дебиторка (B2).
                rd = s + offset
                if rd < n:
                    cash[rd] += amt
                for t in range(s, min(rd, n)):  # дебиторка на конец периодов [s, rd-1]
                    receivables[t] += amt

    return cash, receivables, advances


def cost_timing(accrual: list[Decimal], delay: int, n: int):
    """Распределить издержку по задержке оплаты.

    Возвращает ``(cash, payables)`` — помесячные ряды (кредиторка B23 на конец периода).
    """
    cash = zeros(n)
    payables = zeros(n)
    for s in range(n):
        k = accrual[s]
        if k == 0:
            continue
        pp = s + delay
        if pp < n:
            cash[pp] += k
        for t in range(s, min(pp, n)):  # кредиторка на конец периодов [s, pp-1]
            payables[t] += k
    return cash, payables
