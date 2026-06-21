"""Запасы (SPEC §6, §7): сырьё (B3) и готовая продукция (B5).

Принцип: запасы **капитализируют затраты** — расход признаётся в ОПУ (себестоимостью)
только при продаже, а до этого «лежит» на балансе как актив. Это сохраняет балансовый
инвариант, перенося стоимость из прибыли (себестоимость) в актив (запас) на ту же сумму.

Доказанные тождества (см. комментарии в pipeline):
- сырьё:  ``B3 = cumulative(закупки) − cumulative(потребление)``;
- готовая продукция: ``B5 = cumulative(производств. себестоимость) − cumulative(COGS)``.

НЗП (B4) — отдельная под-часть (требует модели длительности производственного цикла) —
пока не моделируется.
"""
from __future__ import annotations

from decimal import Decimal

from ..money import ZERO
from ..series import zeros


def purchase_schedule(consumption: list[Decimal], stock_lead: int, n: int):
    """Опережающая закупка сырья под потребление.

    Закупка под потребление периода ``c`` происходит за ``stock_lead`` месяцев до него
    (но не раньше старта проекта). Возвращает ``(purchases, raw_inventory)`` — где
    raw_inventory (B3) — остаток сырья на конец периода.
    """
    purchases = zeros(n)
    raw_inventory = zeros(n)
    for c in range(n):
        amt = consumption[c]
        if amt == 0:
            continue
        p = max(0, c - stock_lead)
        purchases[p] += amt
        for t in range(p, c):  # сырьё на складе на конец периодов [p, c-1]
            raw_inventory[t] += amt
    return purchases, raw_inventory


def finished_goods(produced_units: list[Decimal], sold_units: list[Decimal],
                   materials_value: list[Decimal], wages_value: list[Decimal], n: int):
    """Запас готовой продукции по средней себестоимости (агрегированный пул).

    Стоимость производства (материалы + сдельная зарплата) поступает в пул при
    производстве; при продаже признаётся себестоимость (COGS) пропорционально проданной
    доле. Возвращает ``(cogs_materials, cogs_wages, b5, warnings)``.
    """
    cogs_m = zeros(n)
    cogs_w = zeros(n)
    b5 = zeros(n)
    warnings: list[str] = []

    units = ZERO   # единиц в запасе
    vm = ZERO      # стоимость материалов в запасе
    vw = ZERO      # стоимость зарплаты в запасе

    for t in range(n):
        units += produced_units[t]
        vm += materials_value[t]
        vw += wages_value[t]

        if units <= 0:
            # нет единиц в запасе — признаём всю накопленную стоимость как себестоимость
            cogs_m[t] = vm
            cogs_w[t] = vw
            vm = ZERO
            vw = ZERO
            units = ZERO
            b5[t] = ZERO
            continue

        sold = sold_units[t]
        if sold > units:
            warnings.append(f"Период {t}: продажи ({sold}) превышают доступный запас ({units})")
            sold = units
        if sold < 0:
            sold = ZERO

        frac = sold / units if units > 0 else ZERO
        cm = vm * frac
        cw = vw * frac
        cogs_m[t] = cm
        cogs_w[t] = cw
        vm -= cm
        vw -= cw
        units -= sold
        b5[t] = vm + vw

    return cogs_m, cogs_w, b5, warnings
