# Ставка дисконтирования по валюте — план реализации (FC0–FC2)

> Пакет №8 gap-анализа (`GAP-ANALYSIS-PE.md` §1.4): PE считает показатели эффективности
> в обеих валютах проекта — у каждой своя ставка дисконтирования. У нас была одна
> `discount_rate_annual` и показатели только в основной валюте. **Изменение методики**
> (новый выход `metrics_foreign`) → бамп `ENGINE_VERSION`; ставка по валюте не задана
> (0) → блока нет → golden без дрейфа.

## 0. Зафиксированные решения (Q1–Q4)

- **Q1. Что дисконтируем.** Тот же чистый поток до финансирования `CF[t] = C13 + C20`
  (операционная + инвестиционная деятельность), что и основной блок, но **пересчитанный
  во вторую валюту**: `CF_вал[t] = CF[t] / FX[t]`, где `FX[t]` — курс из `_fx_series`
  (единиц основной валюты за единицу второй). Дисконт — своей годовой ставкой валюты
  (`discount_rate_annual_foreign`). Вся машинерия показателей (`build_investment_metrics`)
  переиспользуется — тот же набор NPV/IRR/MIRR/ARR/PI/PB/DPB/потребность в капитале.
- **Q2. Инертность.** `discount_rate_annual_foreign` по умолчанию 0 → `metrics_foreign =
  None` → в снимок не попадает (как budget/participants), в API — `null`. Существующие
  модели считаются как раньше. **Только показатель** — отчёты, баланс, инварианты и
  golden-числа не затрагиваются (показатель есть производная от готового потока).
- **Q3. Самопроверка методики.** Курс 1:1 (`FX≡1`) и та же ставка → `metrics_foreign`
  побайтово равны основным `metrics` (equivalence-тест). Курс, отличный от 1 → NPV во
  второй валюте = `npv(CF/FX, r_вал)` (аналитический тест сверяет с прямым пересчётом
  строк результата).
- **Q4. Версия/golden** — бамп `0.9.38`; ни один семпл не задаёт `discount_rate_annual_
  foreign` → дифф golden = строка версии. UI показывает поле только при наличии второй
  валюты (курс задан); блок показателей на сводке и в DOCX — при непустом `metrics_foreign`.

## 1. Архитектура

```
calc_core/models/project.py       # ProjectSettings.discount_rate_annual_foreign (0 = выкл.)
calc_core/engine/engine.py        # _metrics_foreign(model, cashflow): пересчёт CF по FX + дисконт
                                  # своей ставкой; None при ставке 0; проброс в CalcResult
calc_core/reports/result.py       # CalcResult.metrics_foreign: Optional[InvestmentMetrics]
calc_core/serialize.py            # snapshot["metrics_foreign"] — только при непустом
app/schemas.py                    # CalcResponse.metrics_foreign: Optional[MetricsOut]
app/docgen.py                     # _add_metrics_foreign: раздел «Показатели во второй валюте»
frontend/src/api/model.ts         # ProjectSettings.discount_rate_annual_foreign; Environment.currencies
frontend/src/pages/editor/GeneralTab.tsx        # поле в секции «Дисконтирование» (при 2-й валюте)
frontend/src/pages/ProjectResultsPage.tsx       # блок «Показатели во второй валюте (код)»
```

## 2. Фазы

- [x] **FC0.** Движок: поле `discount_rate_annual_foreign`; `_metrics_foreign` (пересчёт
  `CF/FX` + дисконт своей ставкой; None при 0); `CalcResult.metrics_foreign`; сериализация +
  API-схема; `ENGINE_VERSION=0.9.38` + регенерация golden (дифф = версия). Тесты
  (`test_foreign_metrics.py`): блока нет при ставке 0; NPV = `npv(CF/FX, r_вал)`; курс 1:1 и
  та же ставка → равно основному блоку; отчёты/инвариант при любой ставке не меняются.
- [x] **FC1.** Фронт: типы (`model.ts` + `schema.d.ts` через `gen:api`); поле в GeneralTab
  (видно при заданной второй валюте); блок показателей во второй валюте на сводке
  результатов (NPV/IRR/MIRR/PI/PB/DPB, суммы в коде второй валюты); DOCX-раздел. `tsc` +
  `build` + vitest зелёные.
- [x] **FC2.** Документация: SPEC §17, ROADMAP, GAP-ANALYSIS (1.4 ✅), CLAUDE.md,
  PROJECT-STATUS, чеклист.

## 3. Инварианты

- Ставка по валюте 0 → `metrics_foreign=None` → числа и снимок как раньше (golden = версия).
- Дубль-блок — только показатели: 4 отчёта, баланс `B20=B34` и все прочие выходы не
  зависят от ставки по валюте (проверено: отчёты идентичны при ставке 0 и > 0).
- Курс 1:1 и совпадающие ставки → показатели во второй валюте = основным (equivalence).

**Статус: завершено** (0.9.38). v2-направления: показатели во второй валюте для доходов
участников; шаг дисконтирования (месяц/квартал/полугодие/год) как настройка; выбор валюты
отображения на сводке; расчёт FX-хеджированного потока.
