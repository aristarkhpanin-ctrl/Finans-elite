"""Запасы (SPEC §6, §7): сырьё (B3) и готовая продукция (B5).

Принцип: запасы **капитализируют затраты** — расход признаётся в ОПУ (себестоимостью)
только при продаже, а до этого «лежит» на балансе как актив. Это сохраняет балансовый
инвариант, перенося стоимость из прибыли (себестоимость) в актив (запас) на ту же сумму.

Доказанные тождества (см. комментарии в pipeline):
- сырьё:  ``B3 = cumulative(закупки) − cumulative(потребление)``;
- НЗП:    ``B4 = cumulative(запуск) − cumulative(выпуск)``;
- готовая продукция: ``B5 = cumulative(производств. себестоимость) − cumulative(COGS)``.

Оценка себестоимости ГП (SPEC §22.8): **средняя** (пул) либо **ФИФО** (по партиям выпуска).
Оба метода сохраняют тождество выше (различается лишь распределение стоимости между
себестоимостью проданного и остатком запаса), поэтому баланс сходится при любом методе.

НЗП (B4): при производственном цикле длиной ``cycle`` стоимость запуска (материалы+труд)
и выпуск единиц сдвигаются на ``cycle`` месяцев вперёд (выпуск ГП происходит позже
запуска); стоимость «в пути» копится в B4. При ``cycle = 0`` сдвиг тождественен (B4 ≡ 0).
"""
from __future__ import annotations

from decimal import Decimal

from ..models.common import InventoryMethod
from ..money import ZERO
from ..series import cumulative, zeros


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


def _shift(series: list[Decimal], cycle: int, n: int) -> list[Decimal]:
    """Сдвиг ряда на ``cycle`` месяцев вперёд (значения до сдвига — нули)."""
    out = zeros(n)
    for t in range(n):
        if t - cycle >= 0:
            out[t] = series[t - cycle]
    return out


def work_in_progress(material_cost: list[Decimal], wage_cost: list[Decimal],
                     produced_units: list[Decimal], cycle: int, n: int):
    """Незавершённое производство (НЗП, B4): задержка выпуска на длину цикла.

    Стоимость запуска в производство (материалы + сдельный труд) и выпуск единиц
    сдвигаются на ``cycle`` месяцев — выпуск ГП происходит позже запуска. «В пути»
    стоимость лежит в НЗП: ``B4 = cumulative(запуск) − cumulative(выпуск)``. Возвращает
    ``(material_out, wage_out, produced_out, b4)`` — сдвинутые потоки для пула ГП и остаток
    НЗП. При ``cycle = 0`` — тождественно (выпуск = запуск, B4 ≡ 0).
    """
    if cycle <= 0:
        return material_cost, wage_cost, produced_units, zeros(n)
    material_out = _shift(material_cost, cycle, n)
    wage_out = _shift(wage_cost, cycle, n)
    produced_out = _shift(produced_units, cycle, n)
    started = cumulative([material_cost[t] + wage_cost[t] for t in range(n)])
    finished = cumulative([material_out[t] + wage_out[t] for t in range(n)])
    b4 = [started[t] - finished[t] for t in range(n)]
    return material_out, wage_out, produced_out, b4


def finished_goods(produced_units: list[Decimal], sold_units: list[Decimal],
                   materials_value: list[Decimal], wages_value: list[Decimal], n: int,
                   method: InventoryMethod = InventoryMethod.AVERAGE):
    """Запас готовой продукции: средняя себестоимость или ФИФО (SPEC §6, §22.8).

    Стоимость производства (материалы + сдельная зарплата) капитализуется при выпуске;
    при продаже признаётся себестоимость (COGS). Возвращает
    ``(cogs_materials, cogs_wages, b5, warnings)``.
    """
    if method == InventoryMethod.FIFO:
        return _finished_goods_fifo(produced_units, sold_units, materials_value, wages_value, n)
    return _finished_goods_average(produced_units, sold_units, materials_value, wages_value, n)


def _finished_goods_average(produced_units: list[Decimal], sold_units: list[Decimal],
                            materials_value: list[Decimal], wages_value: list[Decimal], n: int):
    """Средняя себестоимость (агрегированный пул): COGS пропорционально проданной доле."""
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


def _finished_goods_fifo(produced_units: list[Decimal], sold_units: list[Decimal],
                         materials_value: list[Decimal], wages_value: list[Decimal], n: int):
    """ФИФО: продажи списывают самые ранние партии выпуска.

    Каждый выпуск — партия ``[единицы, стоимость материалов, стоимость зарплаты]``. При
    продаже партии расходуются с начала очереди (старейшие); внутри частично списанной
    партии стоимость уменьшается пропорционально доле списанных единиц. Стоимость
    производства без выпуска единиц признаётся себестоимостью сразу (как в средней).
    """
    cogs_m = zeros(n)
    cogs_w = zeros(n)
    b5 = zeros(n)
    warnings: list[str] = []
    layers: list[list[Decimal]] = []  # очередь партий [единицы, мат., зп], старейшие в начале

    for t in range(n):
        if produced_units[t] > 0:
            layers.append([produced_units[t], materials_value[t], wages_value[t]])
        else:
            # стоимость без выпуска единиц → сразу в себестоимость (не оседает в запасе)
            cogs_m[t] += materials_value[t]
            cogs_w[t] += wages_value[t]

        sold = sold_units[t]
        if sold < 0:
            sold = ZERO
        available = sum((layer[0] for layer in layers), ZERO)
        if sold > available:
            warnings.append(f"Период {t}: продажи ({sold}) превышают доступный запас ({available})")
            sold = available

        remaining = sold
        while remaining > 0 and layers:
            lu, lm, lw = layers[0]
            take = lu if remaining >= lu else remaining
            frac = take / lu if lu > 0 else ZERO
            cm, cw = lm * frac, lw * frac
            cogs_m[t] += cm
            cogs_w[t] += cw
            if take >= lu:
                layers.pop(0)
            else:
                layers[0] = [lu - take, lm - cm, lw - cw]
            remaining -= take

        b5[t] = sum((layer[1] + layer[2] for layer in layers), ZERO)

    return cogs_m, cogs_w, b5, warnings
