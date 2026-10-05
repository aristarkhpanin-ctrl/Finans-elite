"""DOCX счёта на оплату и акта оказанных услуг (пакет G, G6).

Бланк строится **только из снимка в самом документе** (``BillingDocument.seller`` /
``buyer`` / суммы / период) — живые реквизиты организации и окружения здесь не читаются
вовсе. Иначе перепечатка через год дала бы другой документ под тем же номером: это уже
не копия первичного документа, а подделка.

Подписи — **только названных людей**: руководитель продавца обязателен (без него
документ не формируется), главный бухгалтер печатается, лишь если задан. Пустая линия под
выдуманной должностью — то, от чего уже отказались реквизиты дела (Прил. Х).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from docx import Document
from docx.shared import Pt

from .closing_docs import service_line
from .db_models import BillingDocument
from .money_words import rubles_in_words

_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря"]


def _date_words(moment) -> str:
    """«26 сентября 2026 г.» — как дату пишут в первичном документе."""
    return f"{moment.day} {_MONTHS[moment.month - 1]} {moment.year} г."


def _money(rub: int | Decimal) -> str:
    """«31 320,00» — разряды пробелом, копейки через запятую."""
    value = Decimal(rub).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, frac = f"{value:.2f}".split(".")
    return f"{int(whole):,}".replace(",", " ") + f",{frac}"


def vat_line(amount_rub: int, rate: int | None) -> tuple[str, str]:
    """Строка НДС: «Без налога (НДС)» либо «В том числе НДС (22%)» и сумма налога.

    НДС — **в цене** (цены прайса — итоговые): налог = сумма × ставка / (100 + ставка),
    округление до копейки.
    """
    if rate is None:
        return "Без налога (НДС)", "—"
    tax = (Decimal(amount_rub) * rate / (100 + rate)).quantize(Decimal("0.01"),
                                                                 rounding=ROUND_HALF_UP)
    return f"В том числе НДС ({rate}%)", _money(tax)


def _party(side: dict, *, seller: bool) -> str:
    name = side.get("name") if seller else side.get("legal_name")
    parts = [str(name or "")]
    if side.get("inn"):
        parts.append(f"ИНН {side['inn']}")
    if side.get("kpp"):
        parts.append(f"КПП {side['kpp']}")
    if side.get("address"):
        parts.append(str(side["address"]))
    return ", ".join(p for p in parts if p)


def _bold(paragraph) -> None:
    for run in paragraph.runs:
        run.bold = True


def _items_table(doc, document: BillingDocument, header_goods: str) -> None:
    table = doc.add_table(rows=2, cols=6)
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells,
                          ("№", header_goods, "Кол-во", "Ед.", "Цена", "Сумма"), strict=True):
        cell.text = text
    for cell, text in zip(table.rows[1].cells,
                          ("1", service_line(document), "1", "усл.",
                           _money(document.amount_rub), _money(document.amount_rub)),
                          strict=True):
        cell.text = text


def _totals(doc, document: BillingDocument, total_label: str) -> None:
    label, tax = vat_line(document.amount_rub, document.seller.get("vat_rate"))
    for text in (f"Итого: {_money(document.amount_rub)}", f"{label}: {tax}",
                 f"{total_label}: {_money(document.amount_rub)}"):
        paragraph = doc.add_paragraph(text)
        _bold(paragraph)


def _signature(doc, role: str, name: str) -> None:
    doc.add_paragraph(f"{role} ____________________ {name}")


def _invoice(doc, d: BillingDocument) -> None:
    s = d.seller
    bank = doc.add_table(rows=6, cols=2)
    bank.style = "Table Grid"
    for row, (label, value) in zip(bank.rows, (
            ("Банк получателя", s.get("bank", "")), ("БИК", s.get("bik", "")),
            ("Корр. счёт", s.get("corr_account", "")), ("Получатель", s.get("name", "")),
            ("ИНН / КПП", " / ".join(v for v in (s.get("inn"), s.get("kpp")) if v)),
            ("Расчётный счёт", s.get("account", ""))), strict=True):
        row.cells[0].text, row.cells[1].text = label, str(value)
    heading = doc.add_paragraph(f"Счёт на оплату № {d.number} от {_date_words(d.doc_date)}")
    _bold(heading)
    heading.runs[0].font.size = Pt(14)
    doc.add_paragraph(f"Поставщик: {_party(s, seller=True)}")
    doc.add_paragraph(f"Покупатель: {_party(d.buyer, seller=False)}")
    _items_table(doc, d, "Товары (работы, услуги)")
    _totals(doc, d, "Всего к оплате")
    doc.add_paragraph(f"Всего наименований 1, на сумму {_money(d.amount_rub)} руб.")
    words = doc.add_paragraph(rubles_in_words(d.amount_rub))
    _bold(words)
    vat_label, vat_sum = vat_line(d.amount_rub, s.get("vat_rate"))
    vat_text = "Без НДС" if s.get("vat_rate") is None else f"{vat_label} {vat_sum}"
    doc.add_paragraph(f"Назначение платежа: оплата по счёту № {d.number} от "
                      f"{d.doc_date.strftime('%d.%m.%Y')}. {vat_text}.")
    # Как счёт превращается в тариф — честно: назначает платформа по поступлению денег.
    doc.add_paragraph("Тариф включается после поступления оплаты: платформа назначает его "
                      "по этому счёту, и оплаченный период начинается с назначения.")
    _signature(doc, "Руководитель", s.get("director", ""))
    if s.get("accountant"):
        _signature(doc, "Главный бухгалтер", s["accountant"])


def _act(doc, d: BillingDocument) -> None:
    s = d.seller
    heading = doc.add_paragraph(f"Акт № {d.number} от {_date_words(d.doc_date)}")
    _bold(heading)
    heading.runs[0].font.size = Pt(14)
    doc.add_paragraph(f"Исполнитель: {_party(s, seller=True)}")
    doc.add_paragraph(f"Заказчик: {_party(d.buyer, seller=False)}")
    _items_table(doc, d, "Наименование услуги")
    _totals(doc, d, "Всего")
    doc.add_paragraph(f"Всего оказано услуг 1, на сумму {_money(d.amount_rub)} руб.")
    words = doc.add_paragraph(rubles_in_words(d.amount_rub))
    _bold(words)
    doc.add_paragraph("Вышеперечисленные услуги оказаны полностью и в срок. Заказчик "
                      "претензий по объёму, качеству и срокам оказания услуг не имеет.")
    _signature(doc, "Исполнитель", s.get("director", ""))
    # Имя заказчика не печатается: подписывает тот, кого назначит покупатель, и
    # вписать за него человека значило бы выдумать подписанта.
    _signature(doc, "Заказчик", "")


def build_document_docx(document: BillingDocument) -> bytes:
    """DOCX документа по его снимку."""
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10)
    (_invoice if document.kind == "invoice" else _act)(doc, document)
    stamp = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    footer = doc.add_paragraph(f"Документ сформирован платформой; копия напечатана {stamp}.")
    footer.runs[0].font.size = Pt(8)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
