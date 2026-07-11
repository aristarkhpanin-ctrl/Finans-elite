# Finans-Elite — заметки для Claude Code

## Редизайн UI («Modal — зелёный куб») — завершён (P0–P13, B1–B5, C1–C5)

- Дизайн-референсы — в `docs/design/modal-redesign/` (`README.md` — маппинг макетов на
  файлы `frontend/src/`, токены и правила). Макеты `*.dc.html` — эталон внешнего вида;
  **точные стили — в `renderVals()` внутри каждого файла**, палитра — только из объекта,
  который **возвращает** `THEME()` (легаси-база внутри THEME переопределена и мертва).
- Итог и статус — `docs/REDESIGN-DECOMPOSITION.md` (все чекбоксы закрыты).
- Файлы макетов в прод не переносятся; импортов из `docs/design/**` в `src/**` быть не должно.
- `styles.css` организован по секциям: 1 токены · 2 база · 3 keyframes · 4 базовые классы ·
  5 UI-кит · 6+ экраны. Новые токены = ключи `THEME()`; при добавлении экрана — новая секция.
- Графики — собственный SVG (`components/charts.tsx`), без сторонних библиотек; палитра —
  токены `--chart-1..7` (живут при смене темы). Помесячный ввод — `MonthlyGrid`.

## Ревью бизнес-плана (Ф10 — вне паритета с Project Expert) — завершено (R0–R10)

- Детерминированный «линтер модели»: `calc_core/review/` — чистые функции над `CalcResult`
  (+ моделью, + опц. стохастикой). Правила по категориям (`rules/`: viability, liquidity,
  structure, assumptions, divergence), каждая находка — `Finding` с числовым `evidence`.
  `run_review(ctx, deep=)` → `ReviewResult` («светофор» + счётчики + отсортированные находки).
- **Ревью только читает результат — движок и golden-master не затрагивает.** Новые правила =
  golden-тест (срабатывание + тишина) в `tests/test_review.py`; `deep=True` включает
  стохастику (MC + чувствительность) для divergence через `enrich_context`.
- Гейт финализации (решение Q4): `POST /projects/{id}/finalize` — risk-находки блокируют до
  `acknowledge`; правка модели (`PUT`) сбрасывает `status` в draft. Методика/решения —
  `docs/PLAN-REVIEW-ADVISOR.md`, `docs/REVIEW-ADVISOR-DECOMPOSITION.md`. UI — вкладка «Ревью плана».

## Точность движка

- Любое изменение методики расчёта — через golden-master (`UPDATE_GOLDEN=1 pytest
  tests/test_golden.py`) с осознанным ревью диффа чисел + аналитические тесты.
  Балансовый инвариант B20=B34 обязан сходиться (property-тесты, 50 моделей).
- Методика — `docs/CALC-ENGINE-SPEC.md`, план — `docs/ROADMAP.md`.

## Команды

- Backend: `cd backend && python -m pytest -q` (все тесты), `uvicorn app.main:app` (dev).
- Frontend: `cd frontend && npx tsc --noEmit && npm run build` (проверка), `npm run dev`.
