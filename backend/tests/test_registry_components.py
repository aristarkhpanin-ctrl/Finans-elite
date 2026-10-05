"""Перечень сторонних компонентов для реестра российского ПО (пакет L, L10).

Перечень собирается из зависимостей, и тест держит его свежим, как снимок OpenAPI:
добавили зависимость, образ или шрифт — файл надо пересобрать. Сверяется **состав**:
лицензии и версии «проверено на» читаются из установленного и на машине CI другие.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import registry_components as rc  # noqa: E402

DOC = rc.OUT.read_text(encoding="utf-8")
REBUILD = "пересоберите: python backend/scripts/registry_components.py"


def test_the_list_matches_the_dependencies():
    expected = {c.name for c in rc.components()}
    listed = rc.listed_names(DOC)
    assert expected == listed, (
        f"{REBUILD}\nнет в файле: {sorted(expected - listed)}\n"
        f"лишние: {sorted(listed - expected)}")


def test_every_image_and_font_has_a_named_license():
    """Образ и шрифт метаданных о лицензии не несут: новый без строки в перечне лицензий
    попал бы в заявку с «не определена»."""
    assert set(rc.images()) <= set(rc.IMAGE_LICENSES), rc.images()
    assert set(rc.fonts()) <= set(rc.FONT_LICENSES), rc.fonts()


def _shipped_rows() -> list[list[str]]:
    section = DOC.split("## Входят в поставку", 1)[1].split("## Только разработка", 1)[0]
    return [[cell.strip() for cell in line.split("|")[1:-1]]
            for line in section.splitlines()
            if line.startswith("| ") and not line.startswith("| Компонент")]


def test_a_copyleft_or_unfree_license_in_the_product_comes_with_words():
    """GPL/LGPL, SSPL, RSAL или «не определена» в поставке без примечания — это вопрос,
    который эксперт задаст первым; ответ должен стоять рядом с компонентом."""
    risky = re.compile(r"GPL|SSPL|RSAL|не определена", re.I)
    silent = [row[0] for row in _shipped_rows() if risky.search(row[2]) and not row[4]]
    assert silent == [], silent


def test_the_list_says_how_it_was_built():
    assert "registry_components.py" in DOC and "Руками не правится" in DOC
