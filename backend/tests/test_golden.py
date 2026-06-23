"""Golden-master тесты расчётного ядра (CALC-ENGINE-SPEC.md §21.3).

Идея: для набора эталонных проектов фиксируется **полный снимок** всех чисел расчёта
(четыре отчёта, показатели эффективности, коэффициенты, безубыточность) в JSON-файле.
Тест пересчитывает проект и сверяет результат со снимком. Любое расхождение —
осознанное изменение методики (тогда снимок обновляют) или регрессия (баг).

Это аналог `clctst32.exe` из оригинала: страховка от незаметного «сползания» цифр и
основа для последующей сверки методики по пунктам §22.

## Обновление эталонов
После намеренного изменения методики снимки перегенерируются:

    UPDATE_GOLDEN=1 pytest tests/test_golden.py

При этом изменения golden-файлов **обязательно** просматриваются в диффе ревью:
видно, какие именно строки и периоды изменились и на сколько.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from calc_core import run
from calc_core.samples import build_sample_project, build_showcase_project
from calc_core.serialize import result_to_dict

GOLDEN_DIR = Path(__file__).parent / "golden"

# Реестр эталонных проектов: имя → фабрика модели.
CASES = {
    "sample_project": build_sample_project,
    "showcase_project": build_showcase_project,
}


def _first_difference(expected, actual, path: str = "") -> str | None:
    """Найти первое расхождение двух JSON-подобных структур (для понятного сообщения)."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in expected.keys() | actual.keys():
            if key not in expected:
                return f"{path}.{key}: появилось значение {actual[key]!r}"
            if key not in actual:
                return f"{path}.{key}: значение пропало (было {expected[key]!r})"
            diff = _first_difference(expected[key], actual[key], f"{path}.{key}")
            if diff:
                return diff
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return f"{path}: длина {len(actual)} != ожидаемой {len(expected)}"
        for i, (e, a) in enumerate(zip(expected, actual)):
            diff = _first_difference(e, a, f"{path}[{i}]")
            if diff:
                return diff
        return None
    if expected != actual:
        return f"{path}: {actual!r} != эталона {expected!r}"
    return None


@pytest.mark.parametrize("name", sorted(CASES))
def test_golden(name: str):
    model = CASES[name]()
    snapshot = result_to_dict(run(model))

    path = GOLDEN_DIR / f"{name}.json"

    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.skip(f"golden обновлён: {name}")

    assert path.exists(), (
        f"Нет эталонного снимка {path.name}. Сгенерируйте: UPDATE_GOLDEN=1 pytest"
    )
    expected = json.loads(path.read_text(encoding="utf-8"))
    diff = _first_difference(expected, snapshot)
    assert diff is None, f"Снимок разошёлся с эталоном [{name}]: {diff}"
