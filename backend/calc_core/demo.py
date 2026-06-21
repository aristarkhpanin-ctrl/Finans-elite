"""Демонстрация работы ядра: ``python -m calc_core.demo``.

Считает демо-проект и печатает ключевые строки отчётов и показатели.
"""
from __future__ import annotations

from decimal import Decimal

from . import run
from .money import quantize
from .samples import build_sample_project


def _fmt(series, codes) -> None:
    pass


def main() -> None:
    model = build_sample_project()
    result = run(model)
    n = result.n

    def row(stmt, code: str) -> str:
        label = stmt.labels[code]
        vals = " ".join(f"{quantize(stmt[code][t]):>12}" for t in range(n))
        return f"{code:>4} {label[:34]:<34} {vals}"

    print(f"Проект: {model.header.name}  (engine {result.engine_version})")
    print(f"Горизонт: {n} мес.\n")

    print("=== ОТЧЁТ О ПРИБЫЛЯХ И УБЫТКАХ (выборка) ===")
    for code in ("I4", "I8", "I23", "I27", "I28"):
        print(row(result.income, code))

    print("\n=== КЭШ-ФЛО (выборка) ===")
    for code in ("C13", "C20", "C27", "C29"):
        print(row(result.cashflow, code))

    print("\n=== БАЛАНС (выборка) ===")
    for code in ("B1", "B11", "B20", "B26", "B33", "B34"):
        print(row(result.balance, code))

    print("\n=== ПОКАЗАТЕЛИ ЭФФЕКТИВНОСТИ (предварительные, v0) ===")
    m = result.metrics
    print(f"NPV  = {quantize(m.npv)}")
    print(f"IRR  = {m.irr_annual if m.irr_annual is None else quantize(Decimal(m.irr_annual) * 100, 1)} %/год")
    print(f"PI   = {None if m.pi is None else quantize(m.pi, 3)}")
    print(f"PB   = {m.pb_months} мес.   DPB = {m.dpb_months} мес.")

    print("\n=== ФИНАНСОВЫЕ КОЭФФИЦИЕНТЫ (последний месяц) ===")
    last = n - 1
    for group_name, group in (("Ликвидность", result.ratios.liquidity),
                              ("Структура капитала", result.ratios.gearing),
                              ("Рентабельность", result.ratios.profitability)):
        print(f"  [{group_name}]")
        for name, series in group.items():
            v = series[last]
            shown = "—" if v is None else str(quantize(v, 3))
            print(f"    {name[:42]:<42} {shown}")

    # быстрая проверка инварианта для наглядности
    ok = all(abs(result.balance["B20"][t] - result.balance["B34"][t]) <= Decimal("0.01") for t in range(n))
    print(f"\nИнвариант баланса B20 = B34: {'OK' if ok else 'НАРУШЕН'}")


if __name__ == "__main__":
    main()
