#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a
. "$HOME/.config/paper-radar/feishu.env"
set +a
export PAPER_RADAR_LOCAL_CODEX_TRANSLATE=1
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
MODE="all"
for arg in "$@"; do
  case "$arg" in
    --prepare) MODE="prepare" ;;
    --send) MODE="send" ;;
  esac
done
cd "$ROOT"
exec flock -n "/tmp/paper-radar-${MODE}.lock" python3 run_daily.py "$@" >> "$ROOT/daily.log" 2>&1
