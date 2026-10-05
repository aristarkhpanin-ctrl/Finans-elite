"""Перечень обрабатываемых персональных данных (пакет L, L11).

Политика обработки ПД называет категории; перечень — где они лежат в базе. Проверяется
в обе стороны: столбец, в котором бывают персональные данные, не может появиться молча
(иначе политика и уведомление Роскомнадзора отстали бы от кода), а строка перечня не
может ссылаться на несуществующий столбец или категорию, которой нет в политике.
"""
from __future__ import annotations

from pathlib import Path

import app.db_models  # noqa: F401 — регистрирует таблицы в метаданных
from app import legal, pd_inventory
from app.database import Base

DOC = Path(__file__).resolve().parents[2] / "docs" / "PD-INVENTORY.md"


def _columns() -> set[str]:
    return {f"{t.name}.{c.name}" for t in Base.metadata.tables.values() for c in t.columns}


def test_every_suspect_column_is_classified():
    """Новый столбец с адресом, именем, автором или свободным текстом обязан попасть в
    перечень (или в NOT_PD с причиной) — иначе он копит персональные данные молча."""
    named = {f.column for f in pd_inventory.FIELDS} | set(pd_inventory.NOT_PD)
    suspect = {c for c in _columns() if pd_inventory.SUSPECT.search(c.split(".", 1)[1])}
    assert suspect - named == set(), sorted(suspect - named)


def test_every_entry_points_at_a_real_column():
    columns = _columns()
    listed = [f.column for f in pd_inventory.FIELDS] + list(pd_inventory.NOT_PD)
    assert [c for c in listed if c not in columns] == []
    assert len({f.column for f in pd_inventory.FIELDS}) == len(pd_inventory.FIELDS)
    assert not {f.column for f in pd_inventory.FIELDS} & set(pd_inventory.NOT_PD)


def test_categories_are_the_policys_and_each_is_somewhere():
    """Категория перечня — та, что в политике (или служебная с причиной), и у каждой
    категории политики есть хоть один столбец: обещание без места хранения — неправда."""
    known = set(pd_inventory.categories())
    assert {f.category for f in pd_inventory.FIELDS} <= known
    used = {f.category for f in pd_inventory.FIELDS}
    assert {c.what for c in legal.PD_CATEGORIES} <= used


def test_the_document_is_fresh():
    assert DOC.read_text(encoding="utf-8") == pd_inventory.render(), (
        "перечень устарел: python backend/scripts/pd_inventory.py")


def test_the_policy_names_what_the_inventory_found():
    """Найденное перечнем политика называет: IP-адрес входа, отписку от веток, реквизиты
    покупателя, отметки автора у объектов."""
    text = " ".join(c.data for c in legal.PD_CATEGORIES)
    for phrase in ("IP-адрес", "отписка от ветки", "реквизиты покупателя", "кто выпустил"):
        assert phrase in text, phrase


def test_the_net_catches_every_known_kind():
    """Сеть для новых столбцов — регулярное выражение по именам. Ослабить её молча нельзя:
    каждый вид столбца, в котором уже нашлись персональные данные, она обязана ловить."""
    kinds = ["email", "full_name", "author_name", "ip", "user_agent", "created_by",
             "body", "mentions", "model", "legal_name", "inn", "legal_address", "label",
             "details", "totp_secret", "hashed_password", "pd_consent_at", "last_seen_at",
             "buyer", "user_id", "actor", "logo", "source", "items"]
    missed = [k for k in kinds if not pd_inventory.SUSPECT.search(k)]
    assert missed == [], missed
