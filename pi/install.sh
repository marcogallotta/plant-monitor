#!/bin/bash
set -euo pipefail

# Assumes Raspberry Pi OS (Debian Bookworm) and user 'pi'.
SCRIPT_DIR="$(dirname "$0")"
INSTALL_DIR="/home/pi/plant-monitoring"
SYSTEMD_DIR="/etc/systemd/system"
UNITS="plant-capture plant-upload plant-cleanup"

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo bash install.sh" >&2
    exit 1
fi

if [[ ! -f "$SCRIPT_DIR/config.json" ]]; then
    read -rp "Backend URL (e.g. http://laptop.local:8000): " backend_url
    echo "{\"backend_url\": \"$backend_url\"}" > "$SCRIPT_DIR/config.json"
    echo "Written to $SCRIPT_DIR/config.json"
fi

echo "==> Installing plant monitoring to $INSTALL_DIR"

mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
chown -R pi:pi "$INSTALL_DIR"

mkdir -p "$INSTALL_DIR/capture" "$INSTALL_DIR/uploaded"
chown pi:pi "$INSTALL_DIR/capture" "$INSTALL_DIR/uploaded"

echo "==> Installing Python dependencies"
apt-get update -q
apt-get install -y python3-picamera2 python3-pil python3-httpx

echo "==> Installing systemd units"
for unit in $UNITS; do
    cp "$INSTALL_DIR/systemd/$unit.service" "$SYSTEMD_DIR/"
    cp "$INSTALL_DIR/systemd/$unit.timer" "$SYSTEMD_DIR/"
done

systemctl daemon-reload

echo "==> Enabling and starting timers"
for unit in $UNITS; do
    systemctl enable --now "$unit.timer"
done

echo ""
echo "Done. Timer status:"
for unit in $UNITS; do
    systemctl status "$unit.timer" --no-pager -l | grep -E "Loaded|Active|Trigger" || true
done

echo ""
echo "Verify with:"
echo "  journalctl -u plant-capture.service -f"
echo "  journalctl -u plant-upload.service -f"
echo "  journalctl -u plant-cleanup.service -f"
