# Finans-Elite

SaaS для финансового моделирования предприятия: расчётное ядро (паритет с
Project Expert 7.21), REST-API и веб-клиент.

Сверх паритета — **ревью бизнес-плана** (Ф10): детерминированный «линтер модели»,
который по итогам расчёта выдаёт находки, рекомендации и «светофор» рисков
(жизнеспособность, ликвидность, структура, допущения, дивергенция план ↔ вероятное
будущее) и служит гейтом перед финализацией плана. Без ИИ, движок не затрагивает.

- **`backend/`** — расчётное ядро `calc_core` (Decimal, 4 отчёта, инвариант B20=B34)
  и FastAPI-приложение (аутентификация, организации, биллинг, холдинги). См.
  [`backend/README.md`](backend/README.md).
- **`frontend/`** — веб-клиент (React + TypeScript + Vite), дизайн-система
  «Modal — зелёный куб». См. [`frontend/README.md`](frontend/README.md).
- **`docs/`** — методика (`CALC-ENGINE-SPEC.md`), архитектура, дорожная карта.

## Запуск полного стека (Docker)

**Всё одной командой** (без предварительной настройки):

```bash
docker compose up --build         # http://localhost:8080
```

Поднимается весь стек — PostgreSQL, Redis, API (FastAPI), фоновый воркер (Celery)
и web (nginx). Отдельно запускать бэкенд и фронт не нужно: единая точка входа —
web на `:8080`, API наружу не публикуется, а проксируется nginx (`/api`,
`/health`), фронт и бэк на одном origin (CORS не нужен). Миграции БД применяются
автоматически при старте API.

По умолчанию — режим разработки с безопасными для локального запуска заглушками.
**Для продакшена** задайте секреты (например, в `.env` рядом с `docker-compose.yml`):

```bash
cp backend/.env.example .env      # APP_ENV=production, JWT_SECRET=<случайный>, POSTGRES_PASSWORD=<...>
docker compose up --build -d
```

В `production` бэкенд fail-fast требует настоящий `JWT_SECRET` (см. `app/security.py`).
Для разработки только ядра/API — `backend/docker-compose.yml` (API + PostgreSQL,
API на `:8000`, `/docs`).

## Разработка

```bash
# Backend
cd backend && pip install ".[dev]" && python -m pytest -q
uvicorn app.main:app --reload            # http://localhost:8000/docs

# Frontend
cd frontend && npm install && npm run dev # http://localhost:5173 (прокси /api → :8000)
```

## Переменные окружения (backend)

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `APP_ENV` | `development` / `production` (в проде JWT_SECRET обязателен) | `development` |
| `DATABASE_URL` | SQLAlchemy URL (в проде — PostgreSQL) | SQLite-файл |
| `JWT_SECRET` | Секрет подписи токенов | dev-заглушка |
| `JWT_TTL_SECONDS` | Срок жизни токена | `86400` |
| `CORS_ORIGINS` | Список origin через запятую (для раздельного деплоя) | пусто |
| `RATE_LIMIT_ENABLED` | Ограничение частоты на `/auth` | `true` |
| `LOG_LEVEL` | Уровень логов (DEBUG/INFO/WARNING/ERROR) | `INFO` |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Redis для фонового анализа | `redis://localhost:6379/0` · `/1` |

Полный список — [`backend/.env.example`](backend/.env.example).
