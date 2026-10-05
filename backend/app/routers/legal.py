"""Публичные документы (пакет L, L5): оферта, политика обработки ПД, согласие, реквизиты.

Читаются **без входа** — их открывают до регистрации и проверяет платёжный агрегатор.
Тексты и реквизиты собирает :mod:`app.legal`; здесь — только перенос в ответ.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import legal
from ..schemas import LegalDocBrief, LegalDocOut, LegalIndexOut, LegalSectionOut

router = APIRouter(prefix="/api/v1/legal", tags=["legal"])


@router.get("", response_model=LegalIndexOut)
def legal_index() -> LegalIndexOut:
    """Список документов и редакция. Пока редакция не утверждена — «черновик»."""
    draft = legal.is_draft()
    return LegalIndexOut(
        edition=legal.edition(), draft=draft, draft_note=legal.DRAFT_NOTE if draft else "",
        documents=[LegalDocBrief(slug=d.slug, title=d.title, summary=d.summary)
                   for d in legal.DOCS.values()])


@router.get("/{slug}", response_model=LegalDocOut)
def legal_doc(slug: str) -> LegalDocOut:
    """Документ с реквизитами продавца; незаданное помечено и перечислено в ``missing``."""
    doc = legal.render(slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="Такого документа нет")
    return LegalDocOut(
        slug=doc.slug, title=doc.title, summary=doc.summary, edition=doc.edition,
        draft=doc.draft, draft_note=legal.DRAFT_NOTE if doc.draft else "",
        sections=[LegalSectionOut(heading=s.heading, paragraphs=list(s.paragraphs))
                  for s in doc.sections],
        missing=doc.missing)
