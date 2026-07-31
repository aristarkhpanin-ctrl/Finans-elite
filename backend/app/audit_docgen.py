"""Генерация документа заключения по анализу отчётности (Финанс-Аудит, фаза E).

Структура: титул → экспертное заключение → аналитическая форма (баланс, ОПУ) →
коэффициенты по группам → диагностика (модели + нормативы). Переиспользует помощники
DOCX первого продукта (``_shrink_table``, ``_fmt_money``, ``DOCX_MIME``).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Optional

from docx import Document

from audit_core.diagnostics import Diagnostics
from audit_core.result import AuditLine, AuditResult
from calc_core.review.text import fmt_num, fmt_pct

from .docgen import DOCX_MIME, _fmt_money, _shrink_table

__all__ = ["DOCX_MIME", "build_audit_docx"]

_ZONE_LABEL = {"safe": "устойчивость", "grey": "неопределённость", "distress": "высокий риск"}
_STATUS_LABEL = {"good": "норма", "warn": "внимание", "risk": "вне норматива"}
_GROUP_TITLES = [
    ("liquidity", "Ликвидность"),
    ("gearing", "Финансовая устойчивость"),
    ("profitability", "Рентабельность"),
    ("activity", "Деловая активность"),
]
#: Показатели-доли выводятся процентами, денежные — рублями, прочие — числом.
_PCT = ("Рентабельность", "Коэффициент автономии", "Суммарные обязательства")
_MONEY = ("Чистый оборотный капитал",)


def _fmt_ratio(name: str, value: Optional[Decimal]) -> str:
    if value is None:
        return "—"
    if name.startswith(_MONEY):
        return _fmt_money(value)
    if name.startswith(_PCT):
        return fmt_pct(value)
    return fmt_num(value)


def _add_table(doc: Document, title: str, periods: list[str],
               rows: list[tuple[str, list[str], bool]]) -> None:
    """Таблица «строка × период»; третий элемент строки — выделять ли жирным (подытог)."""
    doc.add_heading(title, level=1)
    table = doc.add_table(rows=1 + len(rows), cols=1 + len(periods))
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Статья"
    for j, p in enumerate(periods):
        table.rows[0].cells[j + 1].text = p
    for i, (label, values, bold) in enumerate(rows):
        cells = table.rows[i + 1].cells
        cells[0].text = label
        for j, v in enumerate(values):
            cells[j + 1].text = v
        if bold:
            for cell in cells:
                for par in cell.paragraphs:
                    for run in par.runs:
                        run.bold = True
    _shrink_table(table, 8.5)


def _statement_rows(lines: list[AuditLine]) -> list[tuple[str, list[str], bool]]:
    return [(ln.label, [_fmt_money(v) for v in ln.values], ln.subtotal) for ln in lines]


def _add_diagnostics(doc: Document, d: Diagnostics, periods: list[str]) -> None:
    doc.add_heading("Диагностика финансового состояния", level=1)
    doc.add_paragraph(d.summary)
    doc.add_paragraph(f"Оценка выполнена по последнему периоду ({periods[-1]}).")

    scores = [
        (s.name,
         [f"{fmt_num(v)} ({_ZONE_LABEL.get(z, '—')})" if v is not None else "—"
          for v, z in zip(s.values, s.zones, strict=False)],
         False)
        for s in d.scores
    ]
    if scores:
        _add_table(doc, "Модели диагностики банкротства", periods, scores)
        for s in d.scores:
            if s.note:
                doc.add_paragraph(f"{s.name}: {s.note}")

    assessments = [
        (a.name, [_STATUS_LABEL.get(st, "—") if st else "—" for st in a.status], False)
        for a in d.assessments
    ]
    if assessments:
        _add_table(doc, "Оценка показателей по нормативам", periods, assessments)


def build_audit_docx(result: AuditResult, opinion: str, *, subject_name: str,
                     industry: str = "", currency: str = "",
                     today: date | None = None) -> bytes:
    """Собрать документ заключения по анализу и вернуть содержимое ``.docx``."""
    doc = Document()

    doc.add_heading(subject_name or "Субъект анализа", level=0)
    doc.add_paragraph("Заключение по анализу финансового состояния")
    meta = [f"Периодов в анализе: {result.n}"]
    if industry:
        meta.append(f"отрасль: {industry}")
    if currency:
        meta.append(f"валюта: {currency}")
    doc.add_paragraph("; ".join(meta) + ".")
    doc.add_paragraph(f"Дата формирования: {(today or date.today()).strftime('%d.%m.%Y')}.")
    doc.add_paragraph("Финанс-Аудит · анализ по фактической отчётности.")

    doc.add_heading("Экспертное заключение", level=1)
    for block in opinion.split("\n\n"):
        for line in block.split("\n"):
            if line.strip():
                doc.add_paragraph(line.strip())

    if result.n:
        _add_table(doc, "Баланс (аналитическая форма)", result.periods,
                   _statement_rows(result.balance))
        _add_table(doc, "Отчёт о финансовых результатах", result.periods,
                   _statement_rows(result.income))

        for key, title in _GROUP_TITLES:
            series = result.ratios.get(key) or {}
            if not series:
                continue
            rows = [(name, [_fmt_ratio(name, v) for v in values], False)
                    for name, values in series.items()]
            _add_table(doc, f"Коэффициенты — {title.lower()}", result.periods, rows)

        if result.diagnostics is not None:
            _add_diagnostics(doc, result.diagnostics, result.periods)

    if not result.balanced:
        doc.add_paragraph("Внимание: введённая отчётность не сходится (актив ≠ пассив).")

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
