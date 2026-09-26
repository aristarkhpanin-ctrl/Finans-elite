"""Числа в русском написании на входе моделей (`calc_core/decimals.py`).

Пользователь пишет «1 200,50» — так печатает сама платформа и так набирает любой, у кого
русская раскладка. Денежные поля объявлены как ``Decimal``, и такая строка отклоняла
**правку всей модели** с общим «не удалось сохранить»: какое поле виновато, не знал
никто, а введённое пропадало.

Проверяется и то, что нормализация делает, и — не менее важно — то, чего она **не**
делает: неоднозначное значение не угадывается, текстовые поля не трогаются, а уже
валидные числа остаются собой (иначе расчёт зависел бы от разбора ввода).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.schemas import BenchmarkIn
from audit_core.models import AuditSubjectModel, Obligation
from calc_core.decimals import normalize_number
from calc_core.models.investment import Asset
from calc_core.models.operating import SalesLine

D = Decimal


@pytest.mark.parametrize(("raw", "want"), [
    ("5,0", "5.0"),                     # запятая — русский десятичный разделитель
    ("-1250,75", "-1250.75"),
    ("1 200,50", "1200.50"),            # разряды пробелом
    ("1 200,50", "1200.50"),       # неразрывным пробелом — так печатает платформа
    ("1 200", "1200"),             # узким неразрывным
    ("12 345 678", "12345678"),
    (" 7 ", "7"),                       # обрамляющие пробелы
    ("5.0", "5.0"),                     # уже валидное остаётся собой
    ("0", "0"),
])
def test_russian_numbers_are_understood(raw: str, want: str):
    assert normalize_number(raw) == want


@pytest.mark.parametrize("raw", [
    "1 2",              # не разряды: «1 2» — опечатка, а не число
    "1.234,56",         # европейское написание: 1234.56 или 1.234? — не угадываем
    "5,0 руб",          # с единицей измерения
    "5,0,1",
    "",
    "не число",
])
def test_ambiguous_input_is_left_alone(raw: str):
    """Угадывать здесь значило бы поправить не опечатку, а замысел."""
    assert normalize_number(raw) == raw.strip()


def test_model_accepts_a_comma_where_it_used_to_refuse_the_whole_save():
    line = SalesLine.model_validate({"product_id": "p1", "price": ["1 200,50"],
                                     "volume": ["10", "12,5"]})
    assert line.price[0] == D("1200.50") and line.volume[1] == D("12.5")


def test_nested_rows_and_tables_are_covered():
    m = AuditSubjectModel.model_validate({
        "periods": [{"label": "2024", "kind": "year"}],
        "balance": {"A_CASH": ["1 200,50"]},
        "obligations": [{"creditor": "Банк", "amount": "5,0", "rate": "0,14"}],
    })
    assert m.balance["A_CASH"] == [D("1200.50")]
    assert m.obligations[0].amount == D("5.0") and m.obligations[0].rate == D("0.14")


def test_text_fields_are_not_touched():
    """Нормализуются поля, объявленные числом, а не всё подряд."""
    o = Obligation.model_validate({"creditor": "1 200,50", "amount": "1"})
    assert o.creditor == "1 200,50"


def test_ambiguous_value_still_fails_with_a_field_error():
    # Ошибка не исчезла — она осталась там, где действительно неясно, что имелось в виду.
    with pytest.raises(ValueError, match="amount"):
        Obligation.model_validate({"creditor": "Банк", "amount": "1.234,56"})


def test_request_bodies_use_the_same_boundary():
    """Ориентир вводится не в модель, а отдельным запросом — правило то же."""
    assert BenchmarkIn(industry="Перевозки", metric="ev_ebit",
                       value="5,0").value == D("5.0")


def test_already_valid_model_is_untouched():
    """Разбор ввода не меняет числа: расчёт не должен зависеть от написания."""
    raw = {"name": "Станок", "cost": "1000.25", "purchase_month": 0, "life_months": 60}
    assert Asset.model_validate(raw).cost == D("1000.25")
