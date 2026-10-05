"""Собрать пакет для проверки методики (пакет L, L6): docs/METHODOLOGY-REVIEW-PACKET.md.

    python backend/scripts/methodology_packet.py            # пересобрать файл
    python backend/scripts/methodology_packet.py --check    # только сверить свежесть

Пакет собирается из кода — карты методики и движка на демонстрационных моделях, — поэтому
руками его не правят: правка методики → пересборка → свежесть сверяет тест.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from calc_core.methodology_packet import PACKET_PATH, build_packet  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="не писать файл, а только сверить его с кодом")
    args = parser.parse_args()
    target = ROOT / PACKET_PATH
    text = build_packet()
    if args.check:
        fresh = target.exists() and target.read_text(encoding="utf-8") == text
        print("пакет свежий" if fresh else
              "пакет устарел: пересоберите `python backend/scripts/methodology_packet.py`")
        return 0 if fresh else 1
    target.write_text(text, encoding="utf-8")
    print(f"пакет → {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
