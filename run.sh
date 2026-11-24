#!/usr/bin/env bash
# Start the security camera. Extra args go to app.py (--show, --enroll).
set -euo pipefail
cd "$(dirname "$0")"
if [[ " $* " == *" --show "* ]] && [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  export DISPLAY=:0   # started over SSH: put the window on the Pi desktop
fi
exec .venv/bin/python app.py "$@"
