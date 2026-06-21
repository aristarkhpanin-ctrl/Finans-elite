"""Зачёт НДС (SPEC §11).

Метод «по отгрузке»: исходящий НДС (с продаж) признаётся при отгрузке, входной — при
закупке/приобретении. НДС к уплате в бюджет = исходящий − входной − накопленный кредит;
не опускается ниже нуля. Избыток входного НДС переносится вперёд как НДС-кредит (B7,
«Краткосрочные предоплаченные расходы»).

Кэш-фло отражается **с НДС**; ОПУ — **без НДС**. НДС к уплате попадает в строку
«Налоги» (C12).
"""
from __future__ import annotations

from decimal import Decimal

from ..money import ZERO
from ..series import zeros


def settle_vat(vat_out: list[Decimal], vat_in: list[Decimal], n: int):
    """Зачёт НДС с переносом кредита.

    Возвращает ``(vat_to_budget, vat_credit)`` — НДС к уплате в бюджет по месяцам (≥0,
    идёт в C12) и остаток НДС-кредита на конец периода (B7).
    """
    to_budget = zeros(n)
    credit = zeros(n)
    carry = ZERO
    for t in range(n):
        deductible = vat_in[t] + carry      # к вычету: входной за период + накопленный кредит
        payable = vat_out[t]                # к начислению: исходящий за период
        if payable >= deductible:
            to_budget[t] = payable - deductible
            carry = ZERO
        else:
            to_budget[t] = ZERO
            carry = deductible - payable    # избыток входного НДС → кредит вперёд
        credit[t] = carry
    return to_budget, credit
