"""Переоценка статей отчётности (Финанс-Аудит, v2).

Анализ по учётным данным показывает предприятие таким, каким его показывает бухгалтерия.
Аудитору часто нужно посмотреть на него **после поправок**: основные средства учтены по
старой стоимости, часть дебиторки безнадёжна, запасы неликвидны. Переоценка позволяет
задать такие поправки явно и пересчитать весь анализ по скорректированной форме.

Ключевое правило — **у каждой поправки есть корреспонденция в капитале**:

- актив ``+Δ`` → капитал ``+Δ`` (дооценка увеличивает собственные средства);
- обязательство ``+Δ`` → капитал ``−Δ`` (признание долга уменьшает их).

Поэтому равенство «актив = пассив» сохраняется, а исходный разрыв (если отчётность не
сходилась) остаётся прежним — переоценка не «чинит» ввод.

Переоценка **не бывает молчаливой**: каждая применённая поправка попадает в оговорки
результата с суммой и причиной, а результат помечается флагом ``revalued``. Иначе
пользователь мог бы принять скорректированные числа за фактическую отчётность.
"""
from __future__ import annotations

from decimal import Decimal

from .lines import ASSET_CODES, EQLIAB_CODES, LABELS
from .models import AuditSubjectModel

#: Капитал — корреспондирующая статья любой переоценки, поэтому переоценке не подлежит.
COUNTERPART = "P_EQUITY"

#: Статьи, которые можно переоценивать (справочные строки — нет: это расшифровки).
REVALUABLE_CODES: list[str] = [c for c in ASSET_CODES + EQLIAB_CODES if c != COUNTERPART]


def _fit(values: list[Decimal], n: int) -> list[Decimal]:
    """Ряд поправок к числу периодов (недостающие — нули)."""
    out = list(values)[:n]
    while len(out) < n:
        out.append(Decimal(0))
    return out


def apply_revaluations(model: AuditSubjectModel) -> tuple[AuditSubjectModel, list[str]]:
    """Применить переоценки к модели: вернуть скорректированную копию и оговорки.

    Модель без переоценок возвращается **как есть** (тот же объект) — признак инертности:
    ничего не копируется и не пересчитывается, поэтому анализ прежних субъектов не
    меняется ни на разряд.
    """
    active = [r for r in model.revaluations if r.code and any(v for v in r.amounts)]
    if not active:
        return model, []

    n = model.n
    notes: list[str] = []
    balance = {code: list(model.balance_row(code)) for code in ASSET_CODES + EQLIAB_CODES}
    # Справочные строки переносим как есть: они не переоцениваются, но нужны диагностике.
    for code, row in model.balance.items():
        if code not in balance:
            balance[code] = list(row)

    equity = balance[COUNTERPART]
    for rev in active:
        if rev.code == COUNTERPART:
            notes.append(
                f"Переоценка «{rev.label or rev.code}» не применена: капитал — "
                "корреспондирующая статья любой поправки, переоценивать его напрямую "
                "не к чему приравнять.")
            continue
        if rev.code not in REVALUABLE_CODES:
            notes.append(
                f"Переоценка «{rev.label or rev.code}» не применена: статья {rev.code} "
                "не переоценивается (переоценке подлежат статьи баланса, кроме капитала).")
            continue

        amounts = _fit(rev.amounts, n)
        # Обязательство растёт → собственные средства падают; актив растёт → растут.
        sign = Decimal(1) if rev.code in ASSET_CODES else Decimal(-1)
        for t in range(n):
            balance[rev.code][t] += amounts[t]
            equity[t] += sign * amounts[t]

        shown = ", ".join(f"{a:+f}".rstrip("0").rstrip(".") for a in amounts)
        notes.append(
            f"Переоценка: {LABELS.get(rev.code, rev.code)} — {shown}"
            + (f" ({rev.label})" if rev.label else "")
            + f"; корреспонденция — {LABELS[COUNTERPART]}.")

    revalued = model.model_copy(update={"balance": balance, "revaluations": []})
    return revalued, notes
