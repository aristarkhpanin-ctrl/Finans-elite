#!/bin/sh
# Резервные копии базы (пакет L, L11) — сервис backup в docker-compose.yml.
#
# Раз в сутки, в BACKUP_HOUR_UTC часов по UTC, — pg_dump в формате custom; хранятся
# BACKUP_KEEP_DAYS дней. Копия пишется во временный файл и получает имя только целой:
# оборванная копия не выглядит готовой. Старые удаляются только после успешной новой —
# сломанное копирование не съест последние хорошие копии. Раз в RESTORE_CHECK_DAYS дней
# копия разворачивается в отдельную базу и читается (restore-check.sh): копия, которую
# ни разу не разворачивали, — надежда, а не копия.
#
# Итог — отметки в каталоге копий, их читает «Готовность»: LAST_OK (когда, файл, размер,
# ревизия схемы) и LAST_ERROR (когда и почему не удалось). Копии доступны только
# владельцу каталога (umask 077): в них данные всех клиентов; отметки — для чтения всем.
#
#   backup.sh loop   — служба: первая копия сразу, дальше раз в сутки;
#   backup.sh once   — одна копия сейчас (и проверка восстановления, если пора);
#   backup.sh check  — только проверка восстановления последней копии.
set -u
umask 077
DIR=${BACKUP_DIR:-/backups}
KEEP=${BACKUP_KEEP_DAYS:-14}
HOUR=${BACKUP_HOUR_UTC:-1}
CHECK_DAYS=${RESTORE_CHECK_DAYS:-7}
HERE=$(dirname "$0")

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Отметка пишется целиком или никак — «Готовность» не прочтёт половину.
write_mark() {
  printf '%s\n' "$2" > "$DIR/.$1.tmp" && chmod 644 "$DIR/.$1.tmp" && mv "$DIR/.$1.tmp" "$DIR/$1"
}

backup_once() {
  name="finans-$(date -u +%Y%m%dT%H%M%SZ).dump"
  part="$DIR/.$name.partial"
  if pg_dump -Fc -f "$part" 2>"$DIR/.backup.err"; then
    mv "$part" "$DIR/$name"
    bytes=$(wc -c < "$DIR/$name" | tr -d ' ')
    revision=$(psql -tAc "SELECT version_num FROM alembic_version" 2>/dev/null || true)
    write_mark LAST_OK "at=$(now_iso)
file=$name
bytes=$bytes
revision=$revision"
    find "$DIR" -maxdepth 1 -name 'finans-*.dump' -mtime +"$KEEP" -exec rm -f {} \;
    echo "копия $name: $bytes байт"
    return 0
  fi
  rm -f "$part"
  write_mark LAST_ERROR "at=$(now_iso)
error=$(tr '\n' ' ' < "$DIR/.backup.err" | cut -c1-500)"
  echo "копия не удалась: $(cat "$DIR/.backup.err")" >&2
  return 1
}

restore_due() {
  [ -f "$DIR/LAST_RESTORE_CHECK" ] || return 0
  [ -n "$(find "$DIR" -maxdepth 1 -name LAST_RESTORE_CHECK -mtime +"$((CHECK_DAYS - 1))")" ]
}

run_once() {
  backup_once || return 1
  if restore_due; then
    sh "$HERE/restore-check.sh" || true
  fi
}

mkdir -p "$DIR"
# Каталог — для чтения отметок сервисом API; сами копии закрыты (600).
chmod 755 "$DIR"
case "${1:-loop}" in
  once) run_once ;;
  check) sh "$HERE/restore-check.sh" ;;
  loop)
    # Новая установка получает первую копию сразу, а не через сутки.
    [ -f "$DIR/LAST_OK" ] || run_once
    while :; do
      now=$(date -u +%s)
      next=$(( now - now % 86400 + HOUR * 3600 ))
      [ "$next" -gt "$now" ] || next=$(( next + 86400 ))
      sleep $(( next - now ))
      run_once
    done ;;
  *) echo "использование: backup.sh [loop|once|check]" >&2; exit 2 ;;
esac
