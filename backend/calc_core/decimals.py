"""Ввод чисел: запятая как десятичный разделитель и пробелы в разрядах.

Пользователь продукта пишет числа по-русски: «1 200,50». Модели обоих продуктов
объявляют денежные поля как ``Decimal``, а он такую строку не принимает — и правка
всей модели отклонялась целиком, с общим «не удалось сохранить»: какое поле виновато,
не знал никто, а введённое пропадало.

Разбирать это в каждом поле экрана нельзя — полей десятки, и забытое поле снова
уронит сохранение. Поэтому нормализация живёт **в одном месте** — на границе, где
строка становится числом.

Правила намеренно узкие: превращается только то, что читается однозначно.

* ``«5,0» → «5.0»`` — запятая в русском написании и есть десятичный разделитель;
* ``«1 200,50» → «1200.50»`` — пробел (обычный, неразрывный, узкий) разделяет разряды
  **по три цифры**, как их и печатает сама платформа;
* ``«1 2»``, ``«1.234,56»``, ``«5,0 руб»`` — остаются как есть: угадывать здесь
  значило бы поправить не опечатку, а замысел. Такое значение по-прежнему отклоняется
  с обычной ошибкой поля.

Текстовые поля не затрагиваются: нормализуются только поля, объявленные ``Decimal``.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, get_args

from pydantic import BaseModel, model_validator

__all__ = ["MoneyModel", "normalize_number"]

#: Пробелы, которыми разделяют разряды (обычный, неразрывный, узкий неразрывный).
_SPACE = "[ \u00a0\u202f]"

#: Число без разделителей разрядов: «5», «5,0», «-5.25».
_PLAIN = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
#: Число с разрядами по три цифры: «1 200», «1 200,50», «12 345 678».
_GROUPED = re.compile(rf"^[+-]?\d{{1,3}}(?:{_SPACE}\d{{3}})+(?:[.,]\d+)?$")


def normalize_number(raw: str) -> str:
    """Строка ввода → строка, которую принимает ``Decimal`` (или она же, если неясно)."""
    s = raw.strip()
    if _PLAIN.match(s):
        return s.replace(",", ".")
    if _GROUPED.match(s):
        return re.sub(_SPACE, "", s).replace(",", ".")
    return s


def _is_decimal(annotation: Any) -> bool:
    """Объявлено ли поле как ``Decimal`` (в том числе в списке, словаре, ``Optional``)."""
    if annotation is Decimal:
        return True
    return any(_is_decimal(arg) for arg in get_args(annotation))


#: Разбор аннотаций делается один раз на класс: он не меняется, а валидация горячая.
_DECIMAL_FIELDS: dict[type, frozenset[str]] = {}


def _decimal_fields(cls: type[BaseModel]) -> frozenset[str]:
    cached = _DECIMAL_FIELDS.get(cls)
    if cached is None:
        cached = frozenset(name for name, f in cls.model_fields.items()
                           if _is_decimal(f.annotation))
        _DECIMAL_FIELDS[cls] = cached
    return cached


def _normalize(value: Any) -> Any:
    """Нормализовать строку, список строк или словарь рядов — по месту в структуре.

    Когда менять нечего, возвращается **тот же объект**: помесячные ряды длинные, и
    пересобирать их на каждой валидации ради ничего не стоит.
    """
    if isinstance(value, str):
        fixed = normalize_number(value)
        return value if fixed == value else fixed
    if isinstance(value, list):
        items = [_normalize(v) for v in value]
        return value if all(a is b for a, b in zip(items, value, strict=True)) else items
    if isinstance(value, dict):
        rows = {k: _normalize(v) for k, v in value.items()}
        return value if all(rows[k] is v for k, v in value.items()) else rows
    return value


class MoneyModel(BaseModel):
    """База моделей с денежными полями: принимает числа в русском написании.

    Наследование ничего не меняет для уже валидных данных — «5.0» остаётся «5.0», а
    неоднозначное значение по-прежнему отклоняется. Поэтому расчёт от этого не зависит:
    в модель приходят те же числа, что и раньше.
    """

    @model_validator(mode="before")
    @classmethod
    def _normalize_numbers(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data                       # уже собранный объект — трогать нечего
        fields = _decimal_fields(cls)
        patched: dict[str, Any] | None = None
        for name in fields:
            if name not in data:
                continue
            fixed = _normalize(data[name])
            if fixed is not data[name]:
                # Словарь вызывающего не наш: правим копию, а не чужой объект.
                patched = patched if patched is not None else dict(data)
                patched[name] = fixed
        return patched if patched is not None else data
