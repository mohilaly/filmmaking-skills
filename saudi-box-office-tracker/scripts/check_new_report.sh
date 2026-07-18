#!/bin/zsh
# Saudi Box Office watcher — schedule this on a machine in Saudi Arabia (e.g. cron/launchd).
# Checks film.moc.gov.sa for a weekly report image not yet in data/source_image_urls.txt.
# The page is geo-blocked to Saudi IPs, so this must run from a machine in KSA.

# Project root = the directory that contains this scripts/ folder.
PROJ="$(cd "$(dirname "$0")/.." && pwd)"
KNOWN="$PROJ/data/source_image_urls.txt"
LOG="$PROJ/data/check_log.txt"
PAGE="https://film.moc.gov.sa/Box-Office"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S')  $1" >> "$LOG"; }
notify() {
  osascript -e "display notification \"$1\" with title \"Saudi Box Office\" sound name \"Glass\"" >/dev/null 2>&1
  afplay /System/Library/Sounds/Glass.aiff >/dev/null 2>&1
}

html=$(curl -sL --max-time 60 -A "$UA" "$PAGE")
if [ -z "$html" ]; then
  log "ERROR: page unreachable"
  notify "Check ran but the Commission page was unreachable. Will retry at the next scheduled run."
  exit 1
fi

latest=$(echo "$html" \
  | grep -oE 'https://film\.moc\.gov\.sa/-/media/[^"'"'"' ()?]+\.(png|jpg|jpeg|webp)' \
  | grep -iE 'Weekly-Box-Office-Report|weekly-update-infographic' \
  | head -1)

if [ -z "$latest" ]; then
  log "ERROR: page loaded but no report image found (layout may have changed)"
  notify "Check ran but could not find the report image on the page. The page layout may have changed — mention this to Claude."
  exit 1
fi

if grep -qF "$latest" "$KNOWN" 2>/dev/null; then
  log "OK: no new report. Newest on page already captured: ${latest##*/}"
else
  log "NEW: ${latest##*/}"
  notify "New weekly box office report is out. Open Claude Code and say: refresh the box office data"
fi
