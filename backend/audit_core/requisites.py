"""Реквизиты документа и подписи (SPEC, Приложение Х).

Печатный бланк был отчётом о проверке, но не документом сделки: у него не было ни
адресата, ни номера, ни подписи. Печатать пустые линии под выдуманными должностями
было нельзя — Прил. У.4 прямо это запрещало, — и правильный выход не «нарисовать
линии», а завести настоящих подписантов.

Правила слоя:

* **подписи не бывает без имени.** Должность без имени — не подпись, а заготовка;
  такая строка не печатается, но и не пропадает молча: о ней сказано в оговорках;
* **неподписанный документ называет себя рабочим материалом.** Умолчание здесь опаснее
  всего: бланк с гербовой строгостью и без подписи читается как заключение;
* **реквизиты не сверяются с реестром** — доступа к ЕГРЮЛ у платформы нет, и это
  напечатано. Проверяется только внутренняя согласованность ИНН и ОГРН (контрольные
  цифры): опечатка называется, но введённое значение не выбрасывается — это то, что
  ввёл человек, и решать ему.

Слой чистый: читает модель, возвращает свой объект, в ``AuditResult`` не входит.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .models import AuditSubjectModel, ReportRequisites

__all__ = ["RequisitesView", "Signature", "build_requisites", "valid_inn", "valid_ogrn"]

#: Чего платформа с реквизитами не делает. Список печатается вместе с ними: реквизит,
#: который выглядит проверенным, хуже отсутствующего.
NOT_COMPUTED = [
    "Сверка реквизитов с ЕГРЮЛ — доступа к реестру у платформы нет: наименование, ИНН, "
    "ОГРН и адрес введены человеком и приняты как есть.",
    "Проверка полномочий подписанта — платформа не знает ни доверенностей, ни устава "
    "организации; ответственность за подпись несёт тот, кто её ставит.",
]

UNSIGNED = ("Документ не подписан: ни составитель, ни утверждающий не указаны. Это "
            "рабочий материал, а не заключение.")


def _weighted(digits: str, weights: list[int]) -> int:
    """Контрольная цифра по схеме ФНС: взвешенная сумма по модулю 11, затем по 10."""
    return sum(int(d) * w for d, w in zip(digits, weights, strict=False)) % 11 % 10


def valid_inn(value: str) -> bool:
    """ИНН согласован сам с собой: 10 или 12 цифр и сходятся контрольные цифры.

    Это **не** подтверждение существования организации — только защита от опечатки.
    """
    digits = value.strip()
    if not digits.isdigit():
        return False
    if len(digits) == 10:
        return _weighted(digits, [2, 4, 10, 3, 5, 9, 4, 6, 8]) == int(digits[9])
    if len(digits) == 12:
        first = _weighted(digits, [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == int(digits[10])
        second = _weighted(digits, [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == int(digits[11])
        return first and second
    return False


def valid_ogrn(value: str) -> bool:
    """ОГРН согласован сам с собой: 13 или 15 цифр, последняя — контрольная."""
    digits = value.strip()
    if not digits.isdigit() or len(digits) not in (13, 15):
        return False
    base, check = digits[:-1], int(digits[-1])
    divisor = 11 if len(digits) == 13 else 13
    return int(base) % divisor % 10 == check


@dataclass
class Signature:
    """Подписант документа. Существует только вместе с именем."""

    name: str
    role: str


@dataclass
class RequisitesView:
    """Реквизиты документа для всех трёх выходов (экран, DOCX, бланк).

    ``signed`` — есть хотя бы одна подпись. Пустой блок оставляет всё пустым и
    ``signed=False``: это не ошибка, а неподписанный документ, и он так и назван.
    """

    filled: bool = False
    signed: bool = False
    number: str = ""
    #: Дата документа; ``None`` — своей даты нет, печатается дата формирования.
    date: Optional[date] = None
    addressee: str = ""
    subject_full_name: str = ""
    subject_inn: str = ""
    subject_ogrn: str = ""
    subject_address: str = ""
    signatures: list[Signature] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    not_computed: list[str] = field(default_factory=lambda: list(NOT_COMPUTED))


def _signature(name: str, role: str, who: str, caveats: list[str]) -> Optional[Signature]:
    """Подпись из пары «имя + должность»; должность без имени — не подпись."""
    if name.strip():
        return Signature(name=name.strip(), role=role.strip())
    if role.strip():
        # Молча выбросить нельзя: человек заполнил половину и вправе знать, почему
        # строки нет на бумаге.
        caveats.append(f"{who}: указана должность «{role.strip()}» без имени — "
                       "подписи не существует, строка не печатается.")
    return None


def _norm(text: str) -> str:
    """Для сравнения: регистр, кавычки всех видов и пробелы не считаются расхождением."""
    for quote in "«»\"'“”„":
        text = text.replace(quote, "")
    return " ".join(text.upper().split())


#: Чем заменяется «реквизиты с реестром не сверяются», когда снимок реестра есть.
REGISTRY_NOT_EGRUL = ("Сверка — со сведениями ГИР БО (ресурс отчётности ФНС), а не с "
                      "выпиской ЕГРЮЛ: для сделки выписку берут отдельно.")


def _compare_with_registry(view: RequisitesView, model: AuditSubjectModel) -> None:
    """Сверить введённые реквизиты фирмы-цели со снимком реестра (L3).

    Расхождение называется, введённое **не заменяется**: решать, где опечатка — в деле или
    в устаревшем снимке, — человеку. Совпадение тоже называется: «сверено» без перечня
    выглядело бы проверкой всего, а сверяются четыре поля.
    """
    reg = model.registry
    assert reg is not None
    on = reg.fetched_on.strftime("%d.%m.%Y") if reg.fetched_on else "дату запроса"
    pairs = (("ИНН", view.subject_inn, reg.inn), ("ОГРН", view.subject_ogrn, reg.ogrn),
             ("наименование", view.subject_full_name, reg.full_name),
             ("адрес", view.subject_address, reg.address))
    same = [what for what, mine, theirs in pairs
            if mine and theirs and _norm(mine) == _norm(theirs)]
    for what, mine, theirs in pairs:
        if mine and theirs and _norm(mine) != _norm(theirs):
            view.caveats.append(f"{what.capitalize()} в деле («{mine}») расходится со "
                                f"сведениями ГИР БО на {on} («{theirs}»).")
    if same:
        view.caveats.append(f"Совпадают со сведениями ГИР БО на {on}: {', '.join(same)}.")
    view.not_computed = [REGISTRY_NOT_EGRUL if item.startswith("Сверка реквизитов с ЕГРЮЛ")
                         else item for item in view.not_computed]


def build_requisites(model: AuditSubjectModel) -> RequisitesView:
    """Собрать реквизиты документа из модели дела и назвать всё, что не так."""
    r: ReportRequisites = model.report
    caveats: list[str] = []

    signatures = [s for s in (
        _signature(r.executor_name, r.executor_role, "Составитель", caveats),
        _signature(r.approver_name, r.approver_role, "Утверждающий", caveats),
    ) if s is not None]

    inn, ogrn = r.subject_inn.strip(), r.subject_ogrn.strip()
    if inn and not valid_inn(inn):
        caveats.append(f"ИНН «{inn}» не проходит проверку контрольной цифры — похоже на "
                       "опечатку. Значение печатается как введено: сверить его с "
                       "реестром платформа не может.")
    if ogrn and not valid_ogrn(ogrn):
        caveats.append(f"ОГРН «{ogrn}» не проходит проверку контрольной цифры — похоже "
                       "на опечатку. Значение печатается как введено.")

    view = RequisitesView(
        signed=bool(signatures),
        number=r.number.strip(), date=r.date, addressee=r.addressee.strip(),
        subject_full_name=r.subject_full_name.strip(), subject_inn=inn,
        subject_ogrn=ogrn, subject_address=r.subject_address.strip(),
        signatures=signatures, caveats=caveats,
    )
    if model.registry is not None:
        _compare_with_registry(view, model)
    view.filled = bool(view.number or view.date or view.addressee
                       or view.subject_full_name or inn or ogrn
                       or view.subject_address or signatures)
    if not signatures:
        # Оговорка идёт первой: неподписанный документ обязан сказать это раньше всего
        # остального, что он о себе сообщает.
        view.caveats.insert(0, UNSIGNED)
    return view
