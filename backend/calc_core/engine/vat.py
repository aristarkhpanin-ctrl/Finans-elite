"""Зачёт НДС (SPEC §11).

Метод «по отгрузке»: исходящий НДС (с продаж) признаётся при отгрузке, а с полученного
аванса — при получении денег (наиболее ранняя из дат, :func:`output_on_earliest_date`);
входной — при закупке/приобретении. НДС к уплате в бюджет = исходящий − входной −
накопленный кредит; не опускается ниже нуля. Избыток входного НДС переносится вперёд как НДС-кредит (B7,
«Краткосрочные предоплаченные расходы»).

Кэш-фло отражается **с НДС**; ОПУ — **без НДС**. НДС к уплате попадает в строку
«Налоги» (C12).
"""
from __future__ import annotations

from decimal import Decimal

from ..money import ZERO
from ..series import zeros


def output_on_earliest_date(accrued: list[Decimal],
                            advances: list[Decimal]) -> list[Decimal]:
    """Исходящий НДС «по отгрузке» на **наиболее раннюю** из дат (п. 1 ст. 167 НК РФ).

    С полученного аванса НДС начисляется в месяце получения денег, а при отгрузке
    принимается к вычету (п. 8 ст. 171, п. 6 ст. 172). Признание месяца — начисленное по
    отгрузке плюс прирост остатка НДС с авансов на конец месяца; уплаченный НДС с аванса
    лежит в B7 до отгрузки.

    ``advances`` — остаток НДС с авансов по сбыту, собранный **по строкам** тем же
    ``sales_timing``, что ведёт авансы B24. Не «максимум накопленного по отгрузке и по
    оплате»: при смешанных условиях (часть предоплатой, часть с отсрочкой) дебиторка строки
    погасила бы её же аванс, и НДС с аванса снова не начислялся бы. Без авансов признание
    совпадает с начислением.
    """
    out = zeros(len(accrued))
    prev = ZERO
    for t, (vat, adv) in enumerate(zip(accrued, advances, strict=True)):
        out[t] = vat + adv - prev
        prev = adv
    return out


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
