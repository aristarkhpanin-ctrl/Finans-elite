#!/bin/sh
# Проверка восстановления (пакет L, L11): последняя копия разворачивается в отдельную
# базу, из неё читаются ревизия схемы и число организаций и пользователей, база
# удаляется. Итог — отметка LAST_RESTORE_CHECK или LAST_RESTORE_ERROR в каталоге копий.
#
# Проверочная база — на том же сервере: на время проверки нужно место ещё под одну
# копию данных. Запускается суперпользователем базы (как и копирование): роль приложения
# заводить базы не может, и это правильно.
set -u
umask 077
DIR=${BACKUP_DIR:-/backups}
SCRATCH=${RESTORE_CHECK_DB:-finans_restore_check}
file=""

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }
write_mark() {
  printf '%s\n' "$2" > "$DIR/.$1.tmp" && chmod 644 "$DIR/.$1.tmp" && mv "$DIR/.$1.tmp" "$DIR/$1"
}
fail() {
  write_mark LAST_RESTORE_ERROR "at=$(now_iso)
file=$(basename "${file:-нет}")
error=$1"
  dropdb --if-exists "$SCRATCH" >/dev/null 2>&1 || true
  echo "проверка восстановления не прошла: $1" >&2
  exit 1
}
err() { tr '\n' ' ' < "$DIR/.restore.err" | cut -c1-500; }

file=$(ls -1t "$DIR"/finans-*.dump 2>/dev/null | head -n 1)
[ -n "$file" ] || fail "копий нет"
dropdb --if-exists "$SCRATCH" 2>"$DIR/.restore.err" || fail "прежняя проверочная база не удаляется: $(err)"
createdb "$SCRATCH" 2>"$DIR/.restore.err" || fail "проверочная база не создаётся: $(err)"
pg_restore --no-owner --exit-on-error -d "$SCRATCH" "$file" 2>"$DIR/.restore.err" \
  || fail "копия не разворачивается: $(err)"
revision=$(psql -d "$SCRATCH" -tAc "SELECT version_num FROM alembic_version" 2>"$DIR/.restore.err") \
  || fail "в копии нет ревизии схемы: $(err)"
orgs=$(psql -d "$SCRATCH" -tAc "SELECT count(*) FROM organizations" 2>"$DIR/.restore.err") \
  || fail "организации не читаются: $(err)"
users=$(psql -d "$SCRATCH" -tAc "SELECT count(*) FROM users" 2>"$DIR/.restore.err") \
  || fail "пользователи не читаются: $(err)"
dropdb "$SCRATCH" >/dev/null 2>&1 || true
write_mark LAST_RESTORE_CHECK "at=$(now_iso)
file=$(basename "$file")
revision=$revision
organizations=$orgs
users=$users"
echo "восстановление проверено: $(basename "$file"), ревизия $revision, организаций $orgs, пользователей $users"
