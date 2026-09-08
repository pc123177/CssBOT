#!/usr/bin/env bash
set -euo pipefail
SRC=/home/ubuntu/sniper-deals
DEST=/home/ubuntu/sniper-deals/backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
tar -czf "$DEST/state-$STAMP.tar.gz" -C "$SRC" \
  seen_ids.json prices.json health.json settings.json telegram_state.json docs/history.json
find "$DEST" -type f -name 'state-*.tar.gz' -mtime +14 -delete
