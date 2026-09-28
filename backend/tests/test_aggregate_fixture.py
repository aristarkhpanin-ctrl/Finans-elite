"""Свежесть эталонной годовой свёртки (защита экрана от расхождения с документом).

`frontend/src/aggregate.ts` и `app/docgen.py` сворачивают отчёты по одним правилам, но
записаны они дважды. Расхождение означало бы, что один и тот же проект показывает разные
годовые числа в документе и на экране.

Этот тест следит, чтобы файл эталона соответствовал текущему генератору документа;
фронтовый (`aggregate.fixture.test.ts`) — чтобы ему соответствовала свёртка на экране.
Изменил правила свёртки — перегенерируй фикстуру и посмотри, что экран обновлён тоже.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dump_aggregate_fixture import DEFAULT_PATH, build_fixture  # noqa: E402


def test_fixture_matches_docgen():
    """Файл эталона совпадает с тем, что сворачивает генератор документа сейчас."""
    if not DEFAULT_PATH.exists():
        pytest.fail(f"Нет файла {DEFAULT_PATH} — запустите "
                    "python scripts/dump_aggregate_fixture.py")
    on_disk = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    assert on_disk == build_fixture(), (
        "Эталонная свёртка устарела: docgen сворачивает иначе, чем записано в фикстуре.\n"
        "Перегенерируйте: python scripts/dump_aggregate_fixture.py\n"
        "и убедитесь, что aggregate.ts обновлён под те же правила."
    )


def test_fixture_covers_every_rule():
    """Эталон задевает все правила свёртки — иначе сверка экрана ничего не гарантирует."""
    f = build_fixture()
    st = f["statements"]

    # неполный последний год: на нём легче всего ошибиться
    assert f["n"] % 12 != 0
    years = len(st["income"]["yearly"]["I1"])
    assert years == -(-f["n"] // 12)

    # баланс берётся на конец года, а не суммируется
    b20_monthly = next(l for l in st["balance"]["lines"] if l["code"] == "B20")["values"]
    assert st["balance"]["yearly"]["B20"][0] == b20_monthly[11]

    # строка-остаток внутри потокового отчёта: C28 — начало периода
    c28 = next(l for l in st["cashflow"]["lines"] if l["code"] == "C28")["values"]
    assert st["cashflow"]["yearly"]["C28"][1] == c28[12]

    # C29 — конец периода
    c29 = next(l for l in st["cashflow"]["lines"] if l["code"] == "C29")["values"]
    assert st["cashflow"]["yearly"]["C29"][0] == c29[11]

    # потоковая строка действительно суммируется (а не совпала случайно с одним месяцем)
    i1 = next(l for l in st["income"]["lines"] if l["code"] == "I1")["values"]
    assert float(st["income"]["yearly"]["I1"][0]) > float(i1[0])
