#!/usr/bin/env bash
# Install the plant-switchbot systemd timer on the Pi.
# Run from the repo root on your laptop: bash scripts/install_switchbot_pi.sh
set -euo pipefail

PI=marco@plantpi.local
REPO=/home/marco/plant-monitoring

echo "==> Checking Pi reachability"
ssh "$PI" true

echo "==> Checking SWITCHBOT_SENSORS in Pi .env"
ssh "$PI" bash -c "
  source $REPO/.env 2>/dev/null || true
  if [ -z \"\${SWITCHBOT_SENSORS:-}\" ]; then
    echo 'ERROR: SWITCHBOT_SENSORS is not set in $REPO/.env — add it before continuing'
    exit 1
  fi
  echo \"  SWITCHBOT_SENSORS is set\"
"

echo "==> Checking bleak is installed in Pi venv"
ssh "$PI" "$REPO/.venv/bin/python" -c "import bleak" && echo "  bleak ok" || {
  echo "  bleak not found — installing"
  ssh "$PI" "$REPO/.venv/bin/pip" install bleak
}

echo "==> Copying systemd unit files"
scp pi/systemd/plant-switchbot.service pi/systemd/plant-switchbot.timer "$PI:~/.config/systemd/user/"

echo "==> Reloading systemd and enabling timer"
ssh "$PI" bash -c "
  systemctl --user daemon-reload
  systemctl --user enable --now plant-switchbot.timer
"

echo "==> Status"
ssh "$PI" systemctl --user status plant-switchbot.timer --no-pager

echo ""
echo "Done. Run a one-shot test with:"
echo "  ssh $PI systemctl --user start plant-switchbot.service"
echo "  ssh $PI journalctl --user -u plant-switchbot.service -n 50"
