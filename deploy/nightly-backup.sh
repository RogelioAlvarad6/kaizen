#!/usr/bin/env bash
# Nightly backup for the Pi: SIMS tracker DB, Minecraft world, ~/docker configs -> /mnt/data1/backups
# Installed to ~/bin/nightly-backup.sh and run by cron at 03:00. Safe to run by hand any time.
set -uo pipefail

DEST=/mnt/data1/backups
STAMP=$(date +%F)
LOG="$DEST/backup.log"
mkdir -p "$DEST/sims-tracker" "$DEST/minecraft" "$DEST/docker-configs"
log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
fail=0

# 1) Tracker database: consistent copy via SQLite's online backup, made inside the container
if docker exec sims-tracker python -c "import sqlite3; s=sqlite3.connect('/data/sims.db'); d=sqlite3.connect('/data/.nightly.db'); s.backup(d); d.close(); s.close()" \
   && mv -f /mnt/data1/sims-tracker/.nightly.db "$DEST/sims-tracker/sims-$STAMP.db"; then
  log "tracker ok ($(du -h "$DEST/sims-tracker/sims-$STAMP.db" | cut -f1))"
else
  log "tracker FAILED"; fail=1
fi

# 2) Minecraft: pause autosave, flush to disk, archive the world + server config, always resume saving
if docker ps --format '{{.Names}}' | grep -qx minecraft; then
  docker exec minecraft rcon-cli save-off >/dev/null 2>&1
  trap 'docker exec minecraft rcon-cli save-on >/dev/null 2>&1' EXIT
  docker exec minecraft rcon-cli save-all flush >/dev/null 2>&1
  sleep 5
fi
if tar -czf "$DEST/minecraft/world-$STAMP.tar.gz" -C /mnt/data2/minecraft \
     --exclude='data/libraries' --exclude='data/cache' --exclude='data/versions' \
     --exclude='data/logs' --exclude='data/*.jar' data; then
  log "minecraft ok ($(du -h "$DEST/minecraft/world-$STAMP.tar.gz" | cut -f1))"
else
  log "minecraft FAILED"; fail=1
fi
docker exec minecraft rcon-cli save-on >/dev/null 2>&1
trap - EXIT

# 3) Service configs (website, nginx, uptime-kuma, portainer compose files, backlog-api data)
if tar -czf "$DEST/docker-configs/docker-$STAMP.tar.gz" -C "$HOME" \
     --exclude='docker/nginx/logs' --exclude='docker/sims-tracker/src' docker; then
  log "configs ok ($(du -h "$DEST/docker-configs/docker-$STAMP.tar.gz" | cut -f1))"
else
  log "configs FAILED"; fail=1
fi

# 4) Retention: tracker 30 days, Minecraft 7 days, configs 30 days
find "$DEST/sims-tracker" -name 'sims-*.db' -mtime +30 -delete
find "$DEST/minecraft" -name 'world-*.tar.gz' -mtime +7 -delete
find "$DEST/docker-configs" -name 'docker-*.tar.gz' -mtime +30 -delete

summary="failures: $fail · $(df -h /mnt/data1 | awk 'NR==2{print $4" free on data1"}')"
log "done ($summary)"

# Heartbeat to Uptime Kuma (alerts if a backup fails or none happens for 25 h)
[ -f "$HOME/.config/pi-health.env" ] && . "$HOME/.config/pi-health.env"
if [ -n "${KUMA_PUSH_BACKUP:-}" ]; then
  st=$([ $fail -eq 0 ] && echo up || echo down)
  text="$(tail -4 "$LOG" | sed 's/^\[[^]]*\] //' | paste -sd';' | sed 's/;/; /g')"
  [ $fail -ne 0 ] && text="$text  |  WHAT TO DO: 1) Read /mnt/data1/backups/backup.log  2) Re-run by hand: ~/bin/nightly-backup.sh  3) Check space/drive: df -h /mnt/data1 and ~/bin/pi-health.sh -v"
  msg=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$text")
  curl -fsS -m 10 -o /dev/null "$KUMA_PUSH_BACKUP?status=$st&msg=$msg&ping=" || log "kuma push failed"
fi
exit $fail
