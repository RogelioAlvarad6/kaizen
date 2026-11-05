#!/usr/bin/env bash
# Pi health check -> Uptime Kuma push monitors. Runs every 2 minutes from cron (no sudo needed).
#
# Catches the Oct 21 2026 failure: the Minecraft drive went read-only, Paper kept the world in memory,
# and ~22 h of progress never reached disk. Now: Kuma alerts Discord within minutes, and players get
# an in-game warning to stop playing.
#
# Config: ~/.config/pi-health.env
#   KUMA_PUSH_STORAGE=http://<kuma-host>:3001/api/push/XXXX
#   KUMA_PUSH_MINECRAFT=http://<kuma-host>:3001/api/push/YYYY
#   KUMA_PUSH_BACKUP=http://<kuma-host>:3001/api/push/ZZZZ      (used by nightly-backup.sh)
#   PI_DRIVES="/mnt/data1 /mnt/data2"                          (optional, data drives to watch)
#   MINECRAFT_DATA=/mnt/data2/minecraft/data                   (optional)
# Run by hand to see the result:  ~/bin/pi-health.sh -v
set -uo pipefail

CONF="$HOME/.config/pi-health.env"
[ -f "$CONF" ] && . "$CONF"
STATE="$HOME/.cache/pi-health"; mkdir -p "$STATE"
VERBOSE=${1:-}
MC_DATA=${MINECRAFT_DATA:-/mnt/data2/minecraft/data}
DRIVES=${PI_DRIVES:-"/mnt/data1 /mnt/data2"}
MC_DRIVE=$(findmnt -no TARGET --target "$MC_DATA" 2>/dev/null || echo /mnt/data2)

storage_problems=(); storage_info=()
mc_problems=(); mc_info=()

# ---------------- storage ----------------
for m in $DRIVES; do
  name=$(basename "$m")
  if ! mountpoint -q "$m"; then storage_problems+=("$name NOT MOUNTED"); continue; fi
  opts=$(findmnt -no OPTIONS "$m")
  [[ "$opts" == rw* ]] || storage_problems+=("$name mounted READ-ONLY")
  probe="$m/.health-probe"
  if ! (date > "$probe" && rm -f "$probe") 2>/dev/null; then storage_problems+=("$name NOT WRITABLE"); fi
  dev=$(basename "$(findmnt -no SOURCE "$m")")
  errs=$(cat "/sys/fs/ext4/$dev/errors_count" 2>/dev/null || echo 0)
  [ "${errs:-0}" -gt 0 ] && storage_problems+=("$name has $errs filesystem errors")
  pct=$(df --output=pcent "$m" | tail -1 | tr -dc 0-9)
  [ "$pct" -ge 90 ] && storage_problems+=("$name ${pct}% full")
  storage_info+=("$name ${pct}%")
done
sd=$(df --output=pcent / | tail -1 | tr -dc 0-9)
[ "$sd" -ge 90 ] && storage_problems+=("SD card ${sd}% full")
storage_info+=("sd ${sd}%")

# kernel disk errors since the last run (journal is readable via the adm group)
since=$(cat "$STATE/last_run" 2>/dev/null || date -d '-3 min' '+%Y-%m-%d %H:%M:%S')
kerr=$(journalctl -k --since "$since" --no-pager 2>/dev/null \
  | grep -iE "I/O error|EXT4-fs error|remount.*read-only|ata[0-9.]+: (failed|exception|hard resetting|link is slow)|blk_update_request|Buffer I/O error|sd[ab].*(offline|rejecting)" | tail -3)
[ -n "$kerr" ] && storage_problems+=("kernel disk errors: $(echo "$kerr" | tail -1 | cut -c1-140)")
date '+%Y-%m-%d %H:%M:%S' > "$STATE/last_run"

# ---------------- minecraft saves ----------------
if docker ps --format '{{.Names}}' | grep -qx minecraft; then
  # Only real save/disk failures. NOT a bare "IOException": netty logs "NativeIoException ... Connection reset by peer"
  # every time a player's connection drops, which would be a false alarm.
  mcerr=$(docker logs --since 3m minecraft 2>&1 \
    | grep -iE "read-only file system|failed to save|couldn.t save|could not save|No space left on device|Input/output error|java\.io\.IOException: (Read-only|No space|Input/output|Stale)" \
    | grep -viE "NativeIoException|Connection reset|Broken pipe" | tail -1)
  [ -n "$mcerr" ] && mc_problems+=("save error in server log: $(echo "$mcerr" | sed 's/\x1b\[[0-9;]*[mK]//g' | cut -c1-140)")
  if mountpoint -q "$MC_DRIVE" && ! (date > "$MC_DATA/.health-probe" && rm -f "$MC_DATA/.health-probe") 2>/dev/null; then
    mc_problems+=("world folder NOT WRITABLE - progress is not being saved")
  fi
  # Paper autosaves every ~5 min; level.dat older than 30 min means saving has stopped
  if [ -f "$MC_DATA/world/level.dat" ]; then
    age=$(( $(date +%s) - $(stat -c %Y "$MC_DATA/world/level.dat") ))
    [ "$age" -gt 1800 ] && mc_problems+=("world not saved for $((age / 60)) min")
    mc_info+=("last save $((age / 60))m ago")
  fi
  players=$(docker exec minecraft rcon-cli list 2>/dev/null | grep -oE "There are [0-9]+" | grep -oE "[0-9]+")
  mc_info+=("${players:-?} online")
else
  mc_problems+=("minecraft container is not running")
fi

# In-game warning (at most every 20 min) so players stop before losing more progress
if [ ${#mc_problems[@]} -gt 0 ] && docker ps --format '{{.Names}}' | grep -qx minecraft; then
  last=$(cat "$STATE/last_ingame_warn" 2>/dev/null || echo 0)
  if [ $(( $(date +%s) - last )) -gt 1200 ]; then
    docker exec minecraft rcon-cli "say §c[SERVER] Storage error: world progress is NOT being saved right now. Please stop playing until the admin fixes it." >/dev/null 2>&1
    date +%s > "$STATE/last_ingame_warn"
  fi
fi

# ---------------- report to Uptime Kuma ----------------
urlencode() { python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$1"; }
push() {  # url, problems-array-name, info-array-name
  local url=$1; local -n probs=$2; local -n info=$3; local hint=$4
  local status=up msg
  if [ ${#probs[@]} -gt 0 ]; then
    status=down
    msg="$(printf '%s; ' "${probs[@]}")"; msg="${msg%; }"
    msg="$msg  |  WHAT TO DO: $hint"
  else
    msg="OK · $(printf '%s · ' "${info[@]}")"; msg="${msg% · }"
  fi
  [ -n "$VERBOSE" ] && echo "[$status] $msg"
  [ -n "$url" ] && curl -fsS -m 10 -o /dev/null "$url?status=$status&msg=$(urlencode "$msg")&ping=" || true
}
# The hint is appended to every DOWN alert so the Discord message says what to do next.
push "${KUMA_PUSH_STORAGE:-}" storage_problems storage_info \
  "1) Check the drive: findmnt /mnt/data1 /mnt/data2 and sudo smartctl -H -A /dev/sdb  2) If read-only/missing: stop minecraft (docker stop minecraft), reboot the Pi, check power/SATA cables  3) Full status: ~/bin/pi-health.sh -v"
push "${KUMA_PUSH_MINECRAFT:-}" mc_problems mc_info \
  "Players were warned in-game. 1) Check: ~/bin/pi-health.sh -v and docker logs --tail 50 minecraft  2) If the drive is read-only, progress since the last save is lost - reboot the Pi, then compare the world with the newest backup in /mnt/data1/backups/minecraft/  3) Never restore while the server is running"
