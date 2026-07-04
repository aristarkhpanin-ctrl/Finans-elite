# Ревью бизнес-плана — декомпозиция реализации (v1)

> План разработки под фичу «Ревью бизнес-плана» (детерминированный «линтер модели»).
> Оценка осуществимости и обоснование — в [`PLAN-REVIEW-ADVISOR.md`](./PLAN-REVIEW-ADVISOR.md).
> Формат — как `REDESIGN-DECOMPOSITION.md`: фазы R0–R10, каждая = отдельный коммит,
> каждое правило — с golden-тестом. Коды строк — из `calc_core/reports/lines.py`.

---

## 0. Зафиксированные решения (Q1–Q4)

- **Q1 — per-product маржа: НЕ в v1.** Издержки в модели не привязаны к продукту, честная
  юнит-экономика требует доработки модели (BOM). Аллокацию по доле выручки **не делаем**
  (в точностном продукте это вводит в заблуждение). Правило `structure.per_product_margin`
  зарезервировано под **v2** (после BOM). Схема `Finding`/реестр проектируются так, чтобы
  правило доложилось без переделок.
- **Q2 — бенчмарки: НЕ в v1.** Только относительные/внутренние проверки (выбросы,
  несогласованности). Внешний датасет норм не заводим. Абсолютные проверки «дорого/дёшево»
  — опционально в **v3** через *пользовательские* ожидания (ввод «ожидаемая маржа X%»), не ИИ.
- **Q3 — пороги/severity: заданы дефолты** (см. §2, конфиг `ReviewConfig`). Три уровня:
  `risk` (красный) · `warning` (жёлтый) · `info` (синий). «Светофор» резюме — по худшей
  severity. Пороги вынесены в конфиг (глобальные дефолты; per-org — позже). Косвенные
  сигналы — только `info`.
- **Q4 — размещение: ШЛЮЗ ПЕРЕД ФИНАЛИЗАЦИЕЙ ПЛАНА** (решение заказчика). Ревью —
  обязательный этап при финализации: `risk`-находки **блокируют** финализацию, пока
  пользователь явно не подтвердит («ознакомлен, финализировать всё равно»); `warning`/`info`
  не блокируют. Превью ревью доступно и вне шлюза (вкладка результатов).

---

## 1. Модель результата и контекст

### `calc_core/review/types.py`
```python
Severity = Literal["info", "warning", "risk"]
Category = Literal["viability", "liquidity", "structure", "assumptions", "divergence"]

@dataclass(frozen=True)
class Finding:
    id: str                 # "liquidity.cash_gap"
    category: Category
    severity: Severity
    confidence: Literal["high", "medium", "low"]
    title: str              # «Кассовый разрыв в мес. 7»
    detail: str             # объяснение с числами
    recommendation: str
    evidence: dict          # {"month": 7, "value": "-120000", "codes": ["B1"], ...}

@dataclass(frozen=True)
class ReviewResult:
    light: Severity | "ok"  # худшая severity среди находок ("ok" если пусто)
    counts: dict            # {"risk": n, "warning": m, "info": k}
    findings: list[Finding] # отсортированы risk→warning→info

@dataclass
class ReviewContext:
    model: ProjectModel
    result: CalcResult
    mc: MonteCarloResult | None = None          # для divergence; см. §R5
    sensitivity: dict[str, list] | None = None  # param -> точки; см. §R5
```

### `calc_core/review/config.py` — `ReviewConfig` (дефолты)
| Параметр | Дефолт | Где |
|---|---|---|
| `current_ratio_min` | `1.0` | liquidity.current_ratio_low |
| `debt_equity_max` | `2.0` | liquidity.overleverage |
| `interest_coverage_min` | `1.5` (`<1.0`→risk) | liquidity.interest_coverage_low |
| `financing_to_equity_max` | `3.0` | liquidity.financing_dependency |
| `revenue_concentration_max` | `0.70` | structure.revenue_concentration |
| `thin_gross_margin` | `0.10` | structure.thin_gross_margin |
| `cost_outlier_iqr_k` / `cost_outlier_rev_share` | `1.5` / `0.30` | structure.cost_line_outlier |
| `prob_positive_min` | `0.60` | divergence.fragile_positive_npv |
| `dispersion_max` (σ/|mean|) | `1.0` | divergence.wide_dispersion |
| `sensitivity_flip_band` | `±0.10` | divergence.sensitivity_sign_flip |
| MC-дефолт для ревью | uniform ±15% по `sales_price`,`sales_volume`; iters=300, seed=42 | §R5 |
| Sensitivity-дефолт | factors `[0.8,0.9,1.0,1.1,1.2]` по `sales_price`,`sales_volume`,`discount_rate` | §R5 |

---

## 2. Каталог правил (точные формулы, коды из lines.py)

Обозначения: `n` — горизонт (мес.); `Σ` — сумма по всем `t`; строки — ряды по месяцам.
`disc = settings.discount_rate_annual`.

### A. Viability
| id | severity | условие | evidence |
|---|---|---|---|
| `viability.npv_negative` | **risk** | `metrics.npv < 0` | npv, disc |
| `viability.irr_below_hurdle` | warning (**risk** если `npv≤0`) | `irr_annual` задан и `< disc` | irr, disc |
| `viability.irr_undefined` | info | `irr_annual is None` | — |
| `viability.pi_below_one` | warning | `pi` задан и `< 1` | pi |
| `viability.no_payback` | warning | `pb_months is None` | горизонт |
| `viability.irr_unreliable` | info | знак `C13[t]` (ОДП операц.) меняется ≥2 раз | смены знака |

### B. Liquidity
| id | severity | условие | evidence |
|---|---|---|---|
| `liquidity.cash_gap` | **risk** | `∃t: B1[t] < 0` **и** `auto_financing.enabled == False` | худший месяц, глубина |
| `liquidity.financing_dependency` | warning | `peak_financing_need > k·equity`, `equity = ΣC21`, `k=financing_to_equity_max` | peak, equity |
| `liquidity.current_ratio_low` | warning | `min_t(B8[t]/B25[t]) < current_ratio_min` (B25>0) | худший месяц, значение |
| `liquidity.overleverage` | warning | `(B22+B26)/B33` на конец `> debt_equity_max` (B33>0) | значение |
| `liquidity.interest_coverage_low` | warning (**risk** если `<1`) | `ΣI18>0` и `Σ(I23+I18)/ΣI18 < interest_coverage_min` (EBIT=прибыль до налога + проценты; проценты=I18) | коэффициент |

### C. Structure
| id | severity | условие | evidence |
|---|---|---|---|
| `structure.revenue_concentration` | warning | ≥2 продукта и `max_p(выручка_p/Σвыручка) > revenue_concentration_max`; выручка_p = `Σ_t vol×price` (×FX для foreign) из модели | продукт, доля |
| `structure.negative_gross_margin` | **risk** | `ΣI8 < 0` (валовая прибыль суммарно отрицательна) | ΣI8, ΣI4 |
| `structure.thin_gross_margin` | warning | `0 ≤ ΣI8/ΣI4 < thin_gross_margin` | маржа |
| `structure.cost_line_outlier` | warning (conf. medium) | ≥4 статей; статья (direct+fixed) с `Σamount` выбросом (`> Q3+1.5·IQR` тоталов) **и** `> cost_outlier_rev_share·Σвыручка` | статья, сумма, доля |
| `structure.per_product_margin` | — | **v2** (BOM). В v1 не реализуется. | — |

### D. Assumptions (все `info`, confidence low/medium)
| id | условие |
|---|---|
| `assumptions.zero_tax` | `profit_tax_rate == 0` и `ΣI26 > 0` (есть налогооблагаемая база) |
| `assumptions.discount_below_inflation` | `disc < max(inflation_sales,_direct,_wages,_general)` |
| `assumptions.instant_settlement` | все `SalesLine.payment` мгновенные (prepayment=0, оба лага=0) и все лаги издержек 0 → нет оборотного капитала |

### E. Trajectory — **не в v1** (косвенно без бенчмарка; см. PLAN §4.3).

### F. Divergence (переиспользует MC/чувствительность из §R5)
| id | severity | условие | evidence |
|---|---|---|---|
| `divergence.fragile_positive_npv` | warning | `npv > 0` и `mc.probability_npv_positive < prob_positive_min` | npv, P(>0), P5 |
| `divergence.heavy_downside` | warning | `npv > 0` и `mc.npv_p5 < 0` (VaR95 уходит в минус) | P5, CVaR5 |
| `divergence.sensitivity_sign_flip` | warning | по параметру NPV меняет знак внутри factor∈`[1−band, 1+band]` | параметр, factor перелома |
| `divergence.wide_dispersion` | info | `mc.npv_std/|mc.npv_mean| > dispersion_max` | σ/|mean| |

---

## 3. Финализация плана (шлюз, Q4)

### Данные (`db_models.Project`, миграция `review_finalization`)
- `status: str` — `"draft"` (дефолт) | `"finalized"`.
- `finalized_at: datetime | None`.
- `finalized_review: dict | None` — снимок `{light, counts}` на момент финализации.
- `finalized_model_hash: str | None` — sha256 от `model` (детект дрейфа: план изменён после
  финализации).

### Эндпоинты
- `GET /api/v1/projects/{id}/review` → `ReviewResponse` (превью; считает `run(model)`,
  запускает MC/sensitivity по дефолту, гоняет правила). Право `PROJECT_READ`.
- `POST /api/v1/projects/{id}/finalize` (body `{acknowledge: bool = false}`) →
  - считает ревью;
  - если есть `risk` и `acknowledge != true` → **409** с телом `ReviewResponse` (шлюз держит);
  - иначе → `status="finalized"`, сохранить `finalized_at/review/model_hash`; вернуть проект.
  Право `PROJECT_UPDATE`.
- `PUT /projects/{id}` (обновление модели): если был `finalized` → сбросить в `draft`
  (план изменился). Дрейф также виден по несовпадению `finalized_model_hash` с текущим.

### UX (фронт)
- Кнопка **«Финализировать план»** (результаты/редактор) → экран-гейт: светофор + находки
  по severity + для каждого risk чекбокс «ознакомлен». Кнопка «Финализировать» активна,
  когда все risk отмечены (или их нет). При успехе — бейдж **«План финализирован»** +
  дата. Если модель поменяли после — плашка «план изменён после финализации».

---

## 4. Архитектура кода

### Backend
```
calc_core/review/
  __init__.py     # run_review(ctx, config=DEFAULT) -> ReviewResult
  types.py        # Finding, ReviewResult, ReviewContext, Severity, Category
  config.py       # ReviewConfig + DEFAULT_CONFIG
  aggregates.py   # хелперы: total_revenue, gross_margin, per_product_revenue, ebit, ...
  rules/
    __init__.py   # RULES: list[Callable[[Ctx, Cfg], list[Finding]]]
    viability.py  liquidity.py  structure.py  assumptions.py  divergence.py
  runner.py       # прогон реестра, сортировка, светофор
```
- Чисто, детерминированно (в контексте `CALC_CONTEXT`), без БД — как всё ядро.
- `run_review` для divergence сам зовёт `run_monte_carlo`/`run_sensitivity` с дефолт-конфигом
  (seed фиксирован) — воспроизводимо.
```
app/
  schemas.py      # FindingOut, ReviewSummaryOut, ReviewResponse, FinalizeRequest
  routers/review.py  # GET review, POST finalize  (или в projects.py)
  crud.py         # finalize_project, reset_to_draft, model_hash
  db_models.py    # Project.status/finalized_*
  alembic/versions/..._review_finalization.py
```

### Frontend
```
src/api/review.ts               # getReview(id), finalizePlan(id, acknowledge)
src/pages/ProjectResultsPage    # вкладка «Ревью»
src/components/ReviewPanel.tsx   # список находок по severity + светофор + evidence-ссылки
src/components/FinalizeGate.tsx  # модал-гейт финализации (ack рисков)
```
Тяжёлое (MC внутри ревью) — при желании через Celery (async-задача, уже есть).

---

## 5. Фазы (каждая — отдельный коммит; правила — с golden-тестами)

- [ ] **R0. Каркас** `calc_core/review`: types, config, aggregates, пустой runner+реестр.
      Тест: `run_review` на sample → `ReviewResult` валиден, светофор считается.
- [ ] **R1. Viability** (A): 6 правил + тесты (крафт-модели: NPV<0, IRR<hurdle+npv≤0,
      PI<1, нет окупаемости, нестандартный поток).
- [ ] **R2. Liquidity** (B): 5 правил + тесты (кассовый разрыв без автоподбора; зависимость
      от привлечения; низкая текущая ликвидность; леверидж; покрытие процентов).
- [ ] **R3. Structure** (C, без per-product): concentration, negative/thin margin,
      cost_line_outlier + тесты (в т.ч. пограничные пороги).
- [ ] **R4. Assumptions** (D, info): zero_tax, discount<inflation, instant_settlement + тесты.
- [ ] **R5. Divergence** (F): дефолт-прогон MC+sensitivity внутри `run_review`; 4 правила +
      тесты (fragile NPV, VaR<0, sign-flip, дисперсия). Детерминизм по seed.
- [ ] **R6. API ревью**: `ReviewResponse`/`FindingOut`, `GET /projects/{id}/review`,
      маппинг Finding→схема; тесты API (sample-проект → находки; RBAC). Регенерация openapi.
- [ ] **R7. Финализация (шлюз)**: миграция `Project.status/finalized_*`, `POST /finalize`
      (409 при risk без ack; ack → finalized; warning не блокирует), `PUT` сбрасывает в draft,
      hash-дрейф; crud; тесты gate. Регенерация openapi.
- [ ] **R8. Фронт: вкладка «Ревью»**: `ReviewPanel`, светофор, группировка по severity,
      evidence-ссылки на отчёт/период; `api/review.ts`; регенерация типов (`gen:api`).
- [ ] **R9. Фронт: шлюз финализации**: `FinalizeGate`, кнопка, ack рисков, бейдж finalized,
      плашка дрейфа. Компонентный тест (vitest+jsdom) на гейт.
- [ ] **R10. Документация**: ROADMAP (новая фича «Ф10 — Ревью плана», вне паритета с PE),
      README (backend/frontend), закрыть этот чеклист; при необходимости — заметка в
      CALC-ENGINE-SPEC про источники метрик правил.

**Порядок:** R0→R5 (чистое ядро, максимум ценности и тестируемости) → R6 (API) →
R7 (шлюз) → R8–R9 (UI) → R10. R0–R6 дают работающее ревью ещё до UI; шлюз (R7) — отдельно.

---

## 6. Тест-стратегия

- **Golden-по-правилу:** на каждое правило — минимальная крафт-модель, где оно
  срабатывает, и «чистая» модель, где молчит (защита от ложных срабатываний). Значения —
  Decimal, как в `test_golden`/аналитике.
- **Детерминизм:** divergence-правила фиксируют seed MC/sensitivity → стабильные находки.
- **Пороговые:** для конфигурируемых правил — тесты ровно на границе (порог − ε / + ε).
- **API/шлюз:** sample-проект → набор находок; финализация: risk блокирует без ack (409),
  ack финализирует, warning/info не блокируют; `PUT` после финализации → draft.
- **Инвариант культуры:** golden-master движка не трогается (ревью — только чтение
  результата, без изменения методики расчёта).

---

## 7. Явно вне v1 (зафиксировано)
- Per-product маржа (нужен BOM «издержка→продукт») — **v2**.
- Бенчмарки отраслевых норм / пользовательские ожидания — **v3**.
- Правила траектории роста (реализм) — отложены (косвенно без бенчмарка).
- ИИ-формулировка резюме поверх находок — **v4**, опционально.
