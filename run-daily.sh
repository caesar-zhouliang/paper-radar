#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a
. "$HOME/.config/paper-radar/feishu.env"
set +a
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd "$ROOT"
exec flock -n /tmp/paper-radar-daily.lock python3 run_daily.py "$@" >> "$ROOT/daily.log" 2>&1
