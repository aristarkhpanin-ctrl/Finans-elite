# Finans-Elite — заметки для Claude Code

## Редизайн UI («Modal — зелёный куб»)

- Дизайн-референсы — в `docs/design/modal-redesign/` (`README.md` — маппинг макетов на
  файлы `frontend/src/`, токены и правила). Макеты `*.dc.html` — эталон внешнего вида;
  **точные стили — в `renderVals()` внутри каждого файла**, палитра — только из объекта,
  который **возвращает** `THEME()` (легаси-база внутри THEME переопределена и мертва).
- План работ и статус — `docs/REDESIGN-DECOMPOSITION.md` (чекбоксы ведутся по ходу).
- Файлы макетов в прод не переносятся; импортов из `docs/design/**` в `src/**` быть не должно.

## Точность движка

- Любое изменение методики расчёта — через golden-master (`UPDATE_GOLDEN=1 pytest
  tests/test_golden.py`) с осознанным ревью диффа чисел + аналитические тесты.
  Балансовый инвариант B20=B34 обязан сходиться (property-тесты, 50 моделей).
- Методика — `docs/CALC-ENGINE-SPEC.md`, план — `docs/ROADMAP.md`.

## Команды

- Backend: `cd backend && python -m pytest -q` (все тесты), `uvicorn app.main:app` (dev).
- Frontend: `cd frontend && npx tsc --noEmit && npm run build` (проверка), `npm run dev`.
