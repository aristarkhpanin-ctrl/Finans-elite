"""Дамп эталонной годовой свёртки отчётов — общая фикстура для фронтенда.

Зачем. Правила свёртки записаны дважды: `app/docgen.py` сворачивает отчёты по годам для
DOCX-документа, `frontend/src/aggregate.ts` — для переключателя «Месяц | Квартал | Год» на
экране результатов. Правила совпадают дословно (потоки — суммы; баланс — конец периода;
C28/P2 — начало, C29/P7 — конец; P3 = P2 + P1), но ничто не заставляло их совпадать. Если
они разойдутся, один и тот же проект покажет разные годовые числа в документе и на экране —
худший вид расхождения для продукта, который продаёт доверие к числам.

Как. Скрипт считает реальный проект и кладёт рядом вход (четыре отчёта в форме API) и
ожидаемую годовую свёртку из `docgen`. Питоновский тест сверяет файл с регенерацией,
фронтовый прогоняет тот же вход через `aggregate.ts` и сверяет с тем же выходом.

Горизонт намеренно **не кратен 12** — иначе неполный последний год остался бы непроверенным,
а именно на нём легче всего ошибиться.

Запуск: ``python scripts/dump_aggregate_fixture.py [путь]``
(по умолчанию ``frontend/src/fixtures/yearlyAggregate.json``).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.docgen import aggregate_statement  # noqa: E402
from calc_core import run  # noqa: E402
from calc_core.samples import build_showcase_project  # noqa: E402

#: 30 месяцев = два полных года и неполный третий (6 мес.).
N = 30

#: Отчёт → вид свёртки: у баланса все строки берутся на конец периода, у остальных
#: суммируются потоки (кроме строк-остатков C28/P2/C29/P7 — их правила внутри docgen).
STATEMENTS = [("income", "flow"), ("cashflow", "flow"),
              ("balance", "balance"), ("profit_use", "flow")]


def build_fixture() -> dict:
    model = build_showcase_project()
    model.header.duration_months = N
    result = run(model)

    out: dict = {
        "_note": ("Сгенерировано backend/scripts/dump_aggregate_fixture.py — не править "
                  "руками. Вход и ожидаемая годовая свёртка для сверки aggregate.ts "
                  "с app/docgen.py."),
        "n": N,
        "statements": {},
    }
    for key, kind in STATEMENTS:
        stmt = getattr(result, key)
        folded = aggregate_statement(stmt, kind)
        out["statements"][key] = {
            "kind": kind,
            # Вход в форме, которую отдаёт API (StatementOut): код, подпись, ряд строками.
            "lines": [{"code": c, "label": stmt.labels.get(c, c), "values": [str(v) for v in stmt[c]]}
                      for c in stmt.order],
            # Ожидаемая свёртка по годам проекта.
            "yearly": {c: [str(v) for v in folded[c]] for c in stmt.order},
        }
    return out


DEFAULT_PATH = (Path(__file__).resolve().parents[2]
                / "frontend" / "src" / "fixtures" / "yearlyAggregate.json")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(build_fixture(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    print(f"Фикстура годовой свёртки → {path}")


if __name__ == "__main__":
    main()
