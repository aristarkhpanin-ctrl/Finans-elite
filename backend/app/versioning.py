"""Анализ изменений между версиями проекта (пакет №8, gap 4.4).

Чистые функции над JSON-моделями и результатами расчёта — без БД и без побочных
эффектов (удобно тестировать). Диф модели строится по листовым путям (длинные
неизменные ряды не дают шума); диф результатов — по заголовочным показателям.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from calc_core.reports.result import CalcResult

#: Предел числа записей дифа модели (защита от гигантских дифов при смене горизонта).
MODEL_DIFF_LIMIT = 300

#: Заголовочные показатели для дифа результатов: (ключ, метка, «доля ли» для формата).
_METRIC_FIELDS: list[tuple[str, str, bool]] = [
    ("npv", "NPV", False),
    ("irr_annual", "IRR (год)", True),
    ("mirr_annual", "MIRR (год)", True),
    ("pi", "PI", False),
    ("pb_months", "Окупаемость, мес.", False),
    ("dpb_months", "Диск. окупаемость, мес.", False),
    ("peak_financing_need", "Пиковая потребность", False),
]


@dataclass
class ModelChange:
    """Изменение листового значения модели между версиями."""

    path: str
    kind: str            # added | removed | changed
    old: Any = None
    new: Any = None


@dataclass
class MetricChange:
    """Изменение показателя эффективности между версиями (old/new; дельту считает клиент)."""

    key: str
    label: str
    old: Optional[str]
    new: Optional[str]


def flatten_leaves(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Расплющить вложенный JSON в {листовой путь: значение}.

    Словари → ``a.b``; списки → ``a[0]``; остальное — лист. Пустые контейнеры —
    листья (чтобы «был пустой список → стал непустой» тоже попадало в диф).
    """
    out: dict[str, Any] = {}
    if isinstance(obj, dict) and obj:
        for key, value in obj.items():
            out.update(flatten_leaves(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(obj, list) and obj:
        for i, value in enumerate(obj):
            out.update(flatten_leaves(value, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def diff_models(old: dict, new: dict, limit: int = MODEL_DIFF_LIMIT) -> tuple[list[ModelChange], bool]:
    """Диф двух моделей по листовым путям. Возвращает (изменения, усечено ли)."""
    a = flatten_leaves(old)
    b = flatten_leaves(new)
    changes: list[ModelChange] = []
    for path in sorted(set(a) | set(b)):
        if path not in b:
            changes.append(ModelChange(path=path, kind="removed", old=a[path]))
        elif path not in a:
            changes.append(ModelChange(path=path, kind="added", new=b[path]))
        elif a[path] != b[path]:
            changes.append(ModelChange(path=path, kind="changed", old=a[path], new=b[path]))
    truncated = len(changes) > limit
    return changes[:limit], truncated


def _metric_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def diff_metrics(old: CalcResult, new: CalcResult) -> list[MetricChange]:
    """Диф заголовочных показателей эффективности (все поля, включая неизменные)."""
    changes: list[MetricChange] = []
    for key, label, _is_ratio in _METRIC_FIELDS:
        changes.append(MetricChange(
            key=key, label=label,
            old=_metric_str(getattr(old.metrics, key)),
            new=_metric_str(getattr(new.metrics, key)),
        ))
    return changes


#: Заголовочные величины дела для дифа версий (Финанс-Аудит).
#:
#: Это те же величины, что стоят в шапке дела, — и ровно те, из-за которых версию
#: заводят: вердикт, тяжесть находок, охват проверки и цена. Показатели финансового
#: состояния (16 коэффициентов) в диф не идут: они меняются на каждой правке
#: отчётности, и список изменений из них состоял бы целиком, утопив то, ради чего
#: диф смотрят.
_CASE_FIELDS: list[tuple[str, str]] = [
    ("verdict", "Вердикт"),
    ("risk_flags", "Флагов риска"),
    ("warning_flags", "Предупреждений"),
    ("priced_total", "Оценённое влияние флагов"),
    ("coverage", "Охват проверки"),
    ("equity_value", "Стоимость доли"),
]


def diff_case_metrics(old: Any, new: Any) -> list[MetricChange]:
    """Диф заголовочных величин дела по двум разборам (`CaseReview`).

    Величины берутся из готового разбора, а не считаются здесь заново: диф обязан
    показывать то же, что экран, и собственная арифметика разошлась бы с ним.
    ``None`` пробрасывается как ``None`` — «не считалось» не превращается в ноль.
    """
    changes: list[MetricChange] = []
    for key, label in _CASE_FIELDS:
        changes.append(MetricChange(key=key, label=label,
                                    old=_case_value(old, key), new=_case_value(new, key)))
    return changes


def _case_value(review: Any, key: str) -> Optional[str]:
    """Величина разбора по ключу: сводка, охват процедур или оценка."""
    if key == "coverage":
        return _metric_str(review.procedures.coverage)
    if key == "equity_value":
        return _metric_str(review.valuation.equity_value)
    value = getattr(review.summary, key, None)
    # Пустое дело вердикта не имеет: «ok» по умолчанию здесь читался бы как
    # «проверено и всё хорошо», хотя не проверялось ничего.
    if key == "verdict" and review.summary.state != "ready":
        return None
    return _metric_str(value)


def as_decimal(value: Optional[str]) -> Optional[Decimal]:
    """Строка показателя → Decimal (для сортировки/дельт в тестах); None пробрасывается."""
    return None if value is None else Decimal(value)
