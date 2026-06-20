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


def sales_timing(revenue: list[Decimal], terms, n: int):
    """Распределить выручку по условиям оплаты.

    Возвращает ``(cash, receivables, advances)`` — помесячные ряды (на конец периода
    для балансовых B2/B24).
    """
    cash = zeros(n)
    receivables = zeros(n)
    advances = zeros(n)
    a = terms.prepayment_share
    lead = terms.advance_lead_months
    delay = terms.payment_delay_months

    for s in range(n):
        r = revenue[s]
        if r == 0:
            continue
        prepay = a * r
        deferred = r - prepay

        # Предоплата: приходит за `lead` месяцев до поставки s; до поставки — аванс (B24).
        if prepay != 0:
            rp = max(0, s - lead)
            cash[rp] += prepay
            for t in range(rp, s):  # аванс на конец периодов [rp, s-1]
                advances[t] += prepay

        # Остаток: приходит через `delay` после поставки; до получения — дебиторка (B2).
        if deferred != 0:
            rd = s + delay
            if rd < n:
                cash[rd] += deferred
            for t in range(s, min(rd, n)):  # дебиторка на конец периодов [s, rd-1]
                receivables[t] += deferred

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
