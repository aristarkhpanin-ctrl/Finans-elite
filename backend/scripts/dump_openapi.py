"""Дамп OpenAPI-схемы приложения в JSON — контракт для генерации типов фронтенда.

Запуск: ``python scripts/dump_openapi.py [путь]`` (по умолчанию ``backend/openapi.json``).
Вывод детерминирован (sort_keys); CI сверяет закоммиченный файл с регенерацией —
если бэкенд поменял API, а снимок не обновили, шаг падает (защита от дрейфа контракта).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Запуск как скрипта: добавить корень backend в путь, чтобы импортировать пакет app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Схема строится без обращения к БД; движок создаётся лениво, файла не будет.
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.main import app  # noqa: E402 — импорт после настройки окружения


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "openapi.json"
    schema = app.openapi()
    out.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OpenAPI → {out} ({len(schema['paths'])} путей, {len(schema['components']['schemas'])} схем)")


if __name__ == "__main__":
    main()
