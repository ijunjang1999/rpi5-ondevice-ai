#!/usr/bin/env bash
# Start the camera automatically at boot (systemd *user* service - no sudo needed).
# Requires Desktop Autologin (raspi-config) so the user session starts at boot.
#   bash tools/install_service.sh            install + start
#   bash tools/install_service.sh --remove   stop + uninstall
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
UNIT="$HOME/.config/systemd/user/seccam.service"

if [ "${1:-}" = "--remove" ]; then
  systemctl --user disable --now seccam.service 2>/dev/null || true
  rm -f "$UNIT"; systemctl --user daemon-reload
  echo "removed"; exit 0
fi

mkdir -p "$(dirname "$UNIT")" "$DIR/events"
cat > "$UNIT" <<EOF
[Unit]
Description=Raspberry Pi smart security camera + research-time tracker
After=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python $DIR/app.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
StandardOutput=append:$DIR/events/seccam.log
StandardError=append:$DIR/events/seccam.log

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now seccam.service
sleep 3
systemctl --user --no-pager status seccam.service | head -5
if [ "$(loginctl show-user "$USER" -p Linger --value)" != "yes" ]; then
  echo "note: starts at boot via Desktop Autologin. Without autologin run once: sudo loginctl enable-linger $USER"
fi
echo "logs: tail -f $DIR/events/seccam.log    stop: systemctl --user stop seccam"
