-- Роль приложения в базе (пакет L, L11): изоляция организаций (RLS) действует только
-- на роль без прав суперпользователя. Образ postgres делает POSTGRES_USER
-- суперпользователем, а суперпользователь обходит политики RLS всегда, даже с FORCE, —
-- и приложение, подключённое им, видело бы строки всех организаций сразу: держал бы
-- только фильтр приложения, вторая стена изоляции стояла бы на бумаге.
--
-- Скрипт идемпотентный: запускается суперпользователем при каждом старте установки
-- (сервис db-setup в docker-compose.yml) и годится и для новой базы, и для уже
-- работающей — роль заводится, если её нет, и получает владение базой и всеми таблицами
-- схемы public (миграции дальше идут от её имени). Пароль — переменной psql:
--   psql -v app_password="$APP_DB_PASSWORD" -f app-role.sql
\set ON_ERROR_STOP on

SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finans_app') AS need_role \gset
\if :need_role
  CREATE ROLE finans_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
\endif
ALTER ROLE finans_app WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
  PASSWORD :'app_password';

-- Владелец базы — роль приложения: схема public (PostgreSQL 15+) принадлежит владельцу
-- базы, и миграции заводят в ней таблицы от имени приложения.
ALTER DATABASE :"DBNAME" OWNER TO finans_app;
GRANT ALL ON SCHEMA public TO finans_app;

-- Уже существующие объекты (база, заведённая до этой роли) переходят к приложению.
-- Владелец таблицы с FORCE ROW LEVEL SECURITY подчиняется её политикам — ради этого
-- FORCE в миграциях и стоит.
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT c.relname, c.relkind FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')
             AND pg_get_userbyid(c.relowner) <> 'finans_app' LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO finans_app', r.relname);
  END LOOP;
  FOR r IN SELECT c.relname FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relkind = 'S'
             AND pg_get_userbyid(c.relowner) <> 'finans_app' LOOP
    EXECUTE format('ALTER SEQUENCE public.%I OWNER TO finans_app', r.relname);
  END LOOP;
END $$;
