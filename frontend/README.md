# frontend — веб-клиент (React + TypeScript + Vite)

Веб-интерфейс для SaaS финансового моделирования. Этап Ф1: каркас и аутентификация.

## Реализовано (Ф1)
- Vite + React 18 + TypeScript; собственная дизайн-система на CSS (светлая/тёмная тема).
- Маршрутизация (react-router): публичные `/login`, `/register`; защищённые под `Layout`.
- Аутентификация (JWT): контекст `AuthContext`, axios-клиент с подстановкой токена и
  `X-Organization-Id`, авто-выход при 401.
- Выбор организации, переключатель темы, i18n (RU).
- Серверное состояние — TanStack Query; страница списка проектов (read-only).

## Запуск
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (прокси /api → backend :8000)
npm run build      # production-сборка
npm run typecheck  # проверка типов
```
Backend должен быть запущен на :8000 (или задайте `VITE_API_URL`).

## Дальше
- Ф2 — список/создание проектов, редактор модели (формы разделов).
- Ф3 — таблицы отчётов (AG Grid) и коэффициентов, графики (ECharts).
- Ф4 — анализ (чувствительность/Монте-Карло/What-If/безубыточность).
- Ф5 — организация/участники/роли, тарифы и оплата.

## Структура
```
src/
├── main.tsx, App.tsx        # точка входа, маршруты
├── styles.css               # дизайн-токены и базовые стили
├── i18n.ts                  # локализация (RU)
├── api/                     # axios-клиент, типы, методы (auth, projects)
├── auth/                    # AuthContext, ProtectedRoute
├── components/              # Layout, ui (Button/Field/Card), theme
└── pages/                   # LoginPage, RegisterPage, ProjectsPage
```
