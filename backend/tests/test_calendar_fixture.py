"""Свежесть эталонной сметы для фронтенда (защита зеркала от дрейфа).

`frontend/.../calendar.logic.ts` повторяет правила `calc_core/engine/calendar.py`, чтобы
Гантт показывал деньги, пока правки не сохранены. До сих пор числа в тестах обеих сторон
были выписаны руками по отдельности: правка движка роняла питоновские тесты, а зеркало
молча продолжало считать по-старому — и предпросмотр расходился с расчётом.

Теперь обе стороны сверяются с одним файлом. Этот тест следит, чтобы файл соответствовал
текущему движку; фронтовый (`calendar.fixture.test.ts`) — чтобы ему соответствовало
зеркало. Изменил методику сметы — перегенерируй фикстуру и посмотри, что зеркало тоже
обновлено.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dump_calendar_fixture import DEFAULT_PATH, build_fixture  # noqa: E402


def test_fixture_matches_engine():
    """Файл эталона совпадает с тем, что считает движок сейчас."""
    if not DEFAULT_PATH.exists():
        pytest.fail(f"Нет файла {DEFAULT_PATH} — запустите "
                    "python scripts/dump_calendar_fixture.py")
    on_disk = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    assert on_disk == build_fixture(), (
        "Эталонная смета устарела: движок считает иначе, чем записано в фикстуре.\n"
        "Перегенерируйте: python scripts/dump_calendar_fixture.py\n"
        "и убедитесь, что зеркало calendar.logic.ts обновлено под ту же методику."
    )


def test_fixture_covers_every_rule():
    """Эталон задевает все правила сметы — иначе сверка зеркала ничего не гарантирует."""
    f = build_fixture()
    rows = {r["id"]: r for r in f["budget"]["rows"]}

    # все трактовки представлены, включая «без стоимости»
    assert {r["treatment"] for r in rows.values()} == {"expense", "deferred", "asset", "none"}

    # есть этап, у которого оплата отстаёт от освоения (отсрочка ресурса)
    assert any(r["monthly"] != r["monthlyCash"] for r in rows.values())

    # актив: отсрочка ресурса к нему не применяется — оплата совпадает с освоением
    assert rows["s4"]["monthly"] == rows["s4"]["monthlyCash"]

    # группа сворачивает потомков: её стоимость больше стоимости каждого из них
    assert float(rows["g1"]["cost"]) > float(rows["s1"]["cost"])

    # связи «финиш → старт» сдвигают расписание, а не оставляют всё на нуле
    assert rows["s5"]["start"] > 0

    # неоплаченные обязательства где-то ненулевые — иначе разрыв рядов не проверяется
    assert any(v != "0" for v in f["budget"]["payables"])
