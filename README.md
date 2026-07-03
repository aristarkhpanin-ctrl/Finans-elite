# Finans-Elite

SaaS для финансового моделирования предприятия: расчётное ядро (паритет с
Project Expert 7.21), REST-API и веб-клиент.

- **`backend/`** — расчётное ядро `calc_core` (Decimal, 4 отчёта, инвариант B20=B34)
  и FastAPI-приложение (аутентификация, организации, биллинг, холдинги). См.
  [`backend/README.md`](backend/README.md).
- **`frontend/`** — веб-клиент (React + TypeScript + Vite), дизайн-система
  «Modal — зелёный куб». См. [`frontend/README.md`](frontend/README.md).
- **`docs/`** — методика (`CALC-ENGINE-SPEC.md`), архитектура, дорожная карта.

## Запуск полного стека (Docker)

Единая точка входа — web на `:8080`; API наружу не публикуется, а проксируется
nginx (`/api`, `/health`), поэтому фронт и бэк работают на одном origin.

```bash
cp backend/.env.example .env      # заполнить JWT_SECRET (в проде обязателен)
docker compose up --build         # http://localhost:8080
```

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

Полный список — [`backend/.env.example`](backend/.env.example).
