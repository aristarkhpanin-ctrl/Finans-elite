"""Дамп эталонной сметы календарного плана — общая фикстура для фронтенда.

Зачем. `frontend/.../calendar.logic.ts` — зеркало `calc_core/engine/calendar.py`: оно
считает смету и расписание для живого предпросмотра (Гантт), пока правки не отправлены на
сервер. Числа в обоих тестах до сих пор были выписаны руками по отдельности, поэтому
правка движка роняла только питоновские тесты, а зеркало молча продолжало считать
по-старому — и предпросмотр расходился с расчётом.

Как. Скрипт прогоняет через движок модель, задевающую все правила сметы, и кладёт рядом
вход и ожидаемый выход. Питоновский тест сверяет файл с регенерацией (устарел — падает,
как со снимком OpenAPI), фронтовый тест прогоняет тот же вход через зеркало и сверяет с
тем же выходом. Разойтись они теперь не могут: расхождение ловится на одной из сторон.

Запуск: ``python scripts/dump_calendar_fixture.py [путь]``
(по умолчанию ``frontend/src/fixtures/calendarBudget.json``).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calc_core.engine.calendar import compute_budget  # noqa: E402
from calc_core.models import (  # noqa: E402
    CalendarPlan,
    Company,
    InvestmentPlan,
    OperatingPlan,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    Resource,
    Stage,
    StageResource,
    StartingBalance,
)

D = Decimal
N = 12

#: Эталон подобран так, чтобы задеть каждое правило сметы: отсрочку оплаты ресурса,
#: тайминг «в конце», расходы будущих периодов, актив (который отсрочку **не** применяет),
#: этап производства без стоимости, свёртку группы и связь «финиш → старт».
RESOURCES = [
    Resource(id="gen", name="Генподрядчик", unit_price=D("1200000"), payment_delay_months=2),
    Resource(id="eq", name="Поставщик оборудования", unit_price=D("4500000"),
             payment_delay_months=1),
]

STAGES = [
    Stage(id="g1", name="Подготовка площадки"),
    Stage(id="s1", name="Проект и разрешения", parent_id="g1", kind="expense",
          start_month=0, duration_months=2, cost=D("1800000")),
    Stage(id="s2", name="Земляные работы", parent_id="g1", kind="expense",
          predecessor_id="s1", start_month=0, duration_months=2,
          resources=[StageResource(resource_id="gen", quantity=D(3))]),
    Stage(id="s3", name="Лицензия на ПО", kind="expense", start_month=1, duration_months=1,
          cost=D("2400000"), amortize_months=12),
    Stage(id="s4", name="Линия розлива", kind="asset", predecessor_id="s2",
          start_month=0, duration_months=3, asset_life_months=60,
          resources=[StageResource(resource_id="eq", quantity=D(1))]),
    Stage(id="s5", name="Пусконаладка", kind="expense", predecessor_id="s4",
          start_month=0, duration_months=1, cost=D("900000"), cost_timing="on_finish"),
    Stage(id="s6", name="Запуск продукта", kind="production", predecessor_id="s5",
          start_month=0, duration_months=1),
]


def build_model() -> ProjectModel:
    return ProjectModel(
        header=ProjectHeader(name="Календарный эталон", start_date=date(2026, 3, 1),
                             duration_months=N),
        settings=ProjectSettings(discount_rate_annual=D(0), profit_tax_rate=D(0),
                                 property_tax_rate=D(0), vat_rate=D(0)),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(),
        investment_plan=InvestmentPlan(
            calendar=CalendarPlan(stages=STAGES, resources=RESOURCES)),
    )


def _money(v: Decimal) -> str:
    """Деньги строкой — как их отдаёт API (точность без плавающей запятой)."""
    return str(v)


def build_fixture() -> dict:
    model = build_model()
    budget = compute_budget(model, N)
    plan = model.investment_plan.calendar
    return {
        "_note": ("Сгенерировано backend/scripts/dump_calendar_fixture.py — не править "
                  "руками. Вход и ожидаемая смета для сверки зеркала calendar.logic.ts "
                  "с движком calc_core/engine/calendar.py."),
        "n": N,
        "stages": [s.model_dump(mode="json") for s in plan.stages],
        "resources": [r.model_dump(mode="json") for r in plan.resources],
        "budget": {
            "total": _money(budget.total),
            "expenseTotal": _money(budget.expense_total),
            "deferredTotal": _money(budget.deferred_total),
            "assetTotal": _money(budget.asset_total),
            "monthly": [_money(v) for v in budget.monthly],
            "monthlyCash": [_money(v) for v in budget.monthly_cash],
            "cumulative": [_money(v) for v in budget.cumulative],
            "cumulativeCash": [_money(v) for v in budget.cumulative_cash],
            "payables": [_money(v) for v in budget.payables],
            "rows": [
                {
                    "id": s.id,
                    "start": s.start_month,
                    "finish": s.finish_month,
                    "cost": _money(s.cost),
                    "treatment": s.treatment,
                    "monthly": [_money(v) for v in s.monthly],
                    "monthlyCash": [_money(v) for v in s.monthly_cash],
                }
                for s in budget.stages
            ],
        },
    }


DEFAULT_PATH = (Path(__file__).resolve().parents[2]
                / "frontend" / "src" / "fixtures" / "calendarBudget.json")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(build_fixture(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    print(f"Фикстура сметы → {path}")


if __name__ == "__main__":
    main()
