"""Проверка качества введённой отчётности (Финанс-Аудит, макет «Экран 19 — Ошибки данных»).

Зачем отдельный слой. Анализ считает по введённым данным как есть — это правильно: он не
имеет права «чинить» отчётность. Но тогда часть ошибок ввода проявляется не сообщением, а
пустым показателем или неверным сводом, и пользователь узнаёт о них по странному результату.
Здесь те же данные читаются вторым проходом — на предмет того, что с ними не так.

Чистые функции над моделью. **В ``AuditResult`` находки не входят и в golden-снимок не
попадают**: качество ввода — не результат анализа, а высказывание о его входе. Так анализ
остаётся неизменным, а правила проверки можно добавлять, не трогая методику.

Каждая находка несёт числа (``evidence``) и номера затронутых периодов: сообщение без
величины заставляет искать проблему руками, а искать её должен инструмент.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .lines import ASSET_CODES, BALANCE_CODES, INCOME_CODES, LABELS
from .models import AuditSubjectModel

#: Статьи, отрицательное значение в которых учётно невозможно. Капитал сюда не входит:
#: отрицательный капитал — законный и важный факт (непокрытый убыток превысил вклады),
#: и объявлять его ошибкой ввода значило бы прятать худшее, что может показать баланс.
NON_NEGATIVE_CODES = [*ASSET_CODES, "P_LONG", "P_SHORT"]


@dataclass
class InputIssue:
    """Находка проверки ввода: код правила, тяжесть, объяснение и числа."""

    code: str
    #: ``error`` — данные противоречивы, показателям верить нельзя;
    #: ``warning`` — считается, но часть показателей не выйдет;
    #: ``info`` — на числа не влияет, мешает в другом месте (например, в своде группы).
    severity: str
    title: str
    detail: str
    #: Индексы периодов, к которым относится находка (пусто — ко всей модели).
    periods: list[int] = field(default_factory=list)
    evidence: dict[str, Decimal] = field(default_factory=dict)


def _entered(model: AuditSubjectModel, table: str) -> list[str]:
    """Коды строк таблицы, которые пользователь действительно вводил."""
    codes = BALANCE_CODES if table == "balance" else INCOME_CODES
    source = model.balance if table == "balance" else model.income
    return [c for c in codes if source.get(c)]


def _period_labels(n: int, model: AuditSubjectModel) -> list[str]:
    return [model.periods[t].label or f"Период {t + 1}" for t in range(n)]


def check_input(model: AuditSubjectModel) -> list[InputIssue]:
    """Все находки по модели, от тяжёлых к лёгким.

    Пустая модель (нет периодов) находок не даёт: «ничего не введено» — это не ошибка
    ввода, а его отсутствие, и говорить об этом должен пустой экран, а не список проблем.
    """
    n = model.n
    if n == 0:
        return []

    out: list[InputIssue] = []
    names = _period_labels(n, model)
    bal_codes = _entered(model, "balance")
    inc_codes = _entered(model, "income")

    # ── Баланс не сходится ────────────────────────────────────────────────────
    gap = model.balance_gap()
    bad = [t for t in range(n) if gap[t] != 0]
    if bad:
        worst = max(bad, key=lambda t: abs(gap[t]))
        out.append(InputIssue(
            code="balance_gap", severity="error",
            title="Актив не равен пассиву",
            detail=("Расхождение в периодах: "
                    + ", ".join(f"{names[t]} — {gap[t]:+}" for t in bad)
                    + ". Показатели считаются по введённым данным как есть, "
                      "поэтому структурные коэффициенты будут искажены."),
            periods=bad,
            evidence={"max_gap": gap[worst]},
        ))

    # ── Отрицательные значения там, где их не бывает ─────────────────────────
    for code in NON_NEGATIVE_CODES:
        row = model.balance_row(code)
        hit = [t for t in range(n) if row[t] < 0]
        if hit:
            out.append(InputIssue(
                code="negative_line", severity="error",
                title=f"Отрицательное значение: {LABELS.get(code, code)}",
                detail=("Статья не может быть отрицательной: "
                        + ", ".join(f"{names[t]} — {row[t]}" for t in hit)
                        + ". Обычно это перепутанный знак при переносе из отчётности."),
                periods=hit,
                evidence={"min": min(row[t] for t in hit)},
            ))

    # ── Себестоимость без выручки ────────────────────────────────────────────
    rev, cogs = model.income_row("I_REVENUE"), model.income_row("I_COGS")
    hit = [t for t in range(n) if rev[t] == 0 and cogs[t] != 0]
    if hit:
        out.append(InputIssue(
            code="cogs_without_revenue", severity="error",
            title="Себестоимость при нулевой выручке",
            detail=("В периодах " + ", ".join(names[t] for t in hit)
                    + " указана себестоимость, но выручка нулевая. Рентабельность и "
                      "оборачиваемость в этих периодах не определены."),
            periods=hit,
            evidence={"cogs": max(cogs[t] for t in hit)},
        ))

    # ── Нераспределённая прибыль больше капитала ─────────────────────────────
    if model.has_balance_row("M_RETAINED"):
        ret, eq = model.balance_row("M_RETAINED"), model.balance_row("P_EQUITY")
        hit = [t for t in range(n) if ret[t] > eq[t]]
        if hit:
            out.append(InputIssue(
                code="retained_over_equity", severity="warning",
                title="Нераспределённая прибыль превышает капитал",
                detail=("Строка справочная и входит в «Капитал и резервы», поэтому больше "
                        "него быть не может: " + ", ".join(
                            f"{names[t]} — {ret[t]} против {eq[t]}" for t in hit)
                        + ". Модели Альтмана используют эту величину, и оценка сместится."),
                periods=hit,
                evidence={"max_excess": max(ret[t] - eq[t] for t in hit)},
            ))

    # ── Половина отчётности не введена ───────────────────────────────────────
    if bal_codes and not inc_codes:
        out.append(InputIssue(
            code="no_income", severity="warning",
            title="Отчёт о финансовых результатах не введён",
            detail="Без выручки и прибыли не считаются рентабельность, оборачиваемость и "
                   "покрытие процентов, а модели Альтмана теряют два фактора из пяти.",
        ))
    if inc_codes and not bal_codes:
        out.append(InputIssue(
            code="no_balance", severity="warning",
            title="Баланс не введён",
            detail="Без статей баланса не считаются ликвидность, устойчивость и все "
                   "показатели, где знаменатель — актив или капитал.",
        ))

    # ── Пустые периоды ───────────────────────────────────────────────────────
    if bal_codes or inc_codes:
        empty = [t for t in range(n)
                 if all(model.balance_row(c)[t] == 0 for c in bal_codes)
                 and all(model.income_row(c)[t] == 0 for c in inc_codes)]
        if empty:
            out.append(InputIssue(
                code="empty_period", severity="warning",
                title="Период без данных",
                detail=("Ни одна статья не заполнена: " + ", ".join(names[t] for t in empty)
                        + ". Такой период войдёт в тренды нулями и покажет падение на 100%, "
                          "которого не было."),
                periods=empty,
            ))

    # ── Подписи периодов ─────────────────────────────────────────────────────
    # Свод группы сопоставляет периоды участников по подписи. Без подписи период в свод
    # не попадёт вовсе, при совпадении подписей второй будет молча отброшен.
    blank = [t for t in range(n) if not model.periods[t].label]
    if blank:
        out.append(InputIssue(
            code="blank_period_label", severity="info",
            title="Период без подписи",
            detail=(f"Периодов без подписи: {len(blank)}. На экране они называются по "
                    "номеру, но в свод группы такой период не попадёт: участники "
                    "сопоставляются именно по подписи."),
            periods=blank,
        ))

    seen: dict[str, int] = {}
    dupes: list[int] = []
    for t in range(n):
        label = model.periods[t].label
        if not label:
            continue
        if label in seen:
            dupes.append(t)
        else:
            seen[label] = t
    if dupes:
        out.append(InputIssue(
            code="duplicate_period_label", severity="error",
            title="Повторяющаяся подпись периода",
            detail=("Подписи повторяются: "
                    + ", ".join(sorted({model.periods[t].label for t in dupes}))
                    + ". В своде группы из одинаковых подписей будет учтена только первая, "
                      "и данные остальных периодов пропадут из суммы."),
            periods=dupes,
        ))

    order = {"error": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda i: order[i.severity])
