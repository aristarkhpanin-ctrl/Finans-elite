"""Перечень обрабатываемых персональных данных (пакет L, L11) → docs/PD-INVENTORY.md.

Запуск: ``python backend/scripts/pd_inventory.py`` — пишет файл; ``--check`` — только
сверка свежести. Состав перечня — ``app/pd_inventory.py``; тест
``tests/test_pd_inventory.py`` держит его в обе стороны со столбцами базы.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pd_inventory import render  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "PD-INVENTORY.md"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        fresh = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("перечень свежий" if fresh else
              "перечень устарел: python backend/scripts/pd_inventory.py")
        return 0 if fresh else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"перечень ПД → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
