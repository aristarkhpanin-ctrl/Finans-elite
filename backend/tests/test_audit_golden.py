"""Golden-master анализа Финанс-Аудит (продукт №2).

Тот же принцип, что у первого продукта: полный снимок всех чисел анализа фиксируется в
JSON и сверяется при каждом прогоне. Снимки аудита **независимы** от golden первого
продукта — методики продуктов не пересекаются.

Обновление эталонов после осознанного изменения методики:

    UPDATE_AUDIT_GOLDEN=1 pytest tests/test_audit_golden.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from test_golden import _first_difference  # общий помощник сравнения снимков

from audit_core import analyze
from audit_core.samples import build_quarterly_subject, build_trading_subject
from audit_core.serialize import result_to_dict

GOLDEN_DIR = Path(__file__).parent / "golden_audit"

CASES = {
    "trading_subject": build_trading_subject,
    "quarterly_subject": build_quarterly_subject,
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_audit_golden(name: str):
    snapshot = result_to_dict(analyze(CASES[name]()))
    path = GOLDEN_DIR / f"{name}.json"

    if os.environ.get("UPDATE_AUDIT_GOLDEN"):
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.skip(f"golden аудита обновлён: {name}")

    assert path.exists(), (
        f"Нет эталонного снимка {path.name}. Сгенерируйте: UPDATE_AUDIT_GOLDEN=1 pytest"
    )
    expected = json.loads(path.read_text(encoding="utf-8"))
    diff = _first_difference(expected, snapshot)
    assert diff is None, f"Снимок анализа разошёлся с эталоном [{name}]: {diff}"


def test_golden_subjects_are_balanced():
    """Эталоны корректны: актив = пассив во всех периодах."""
    for name, build in CASES.items():
        assert build().is_balanced(), f"эталон {name}: баланс не сходится"
