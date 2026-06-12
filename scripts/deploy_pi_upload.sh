#!/usr/bin/env bash
# Deploy pi/upload.py to the live Raspberry Pi install and smoke-test it.
# Run from the repo root on your laptop: bash scripts/deploy_pi_upload.sh
set -euo pipefail

PI=${PI:-marco@plantpi.local}
INSTALL_DIR=${INSTALL_DIR:-/home/pi/plant-monitoring}
STAGED=${STAGED:-/tmp/plant-upload.py}
LOCAL_UPLOAD=${LOCAL_UPLOAD:-pi/upload.py}

if [ ! -f "$LOCAL_UPLOAD" ]; then
  echo "ERROR: $LOCAL_UPLOAD not found. Run this from the repo root." >&2
  exit 1
fi

echo "==> Checking Pi reachability"
ssh "$PI" true

echo "==> Staging $LOCAL_UPLOAD on $PI:$STAGED"
scp "$LOCAL_UPLOAD" "$PI:$STAGED"

echo "==> Diffing staged uploader against installed uploader"
ssh "$PI" sudo diff -u "$STAGED" "$INSTALL_DIR/upload.py" || true

echo "==> Installing uploader"
ssh "$PI" sudo install -o pi -g pi -m 0644 "$STAGED" "$INSTALL_DIR/upload.py"

echo "==> Verifying installed uploader matches staged file"
ssh "$PI" sudo diff -u "$STAGED" "$INSTALL_DIR/upload.py"

echo "==> Running upload smoke test"
ssh "$PI" "sudo bash -lc 'cd \"$INSTALL_DIR\" && python3 upload.py capture'"

echo "==> Remaining capture files"
ssh "$PI" sudo find "$INSTALL_DIR/capture" -maxdepth 1 -type f | sort

echo "==> plant-upload timer status"
ssh "$PI" sudo systemctl status plant-upload.timer --no-pager -l

echo "Done. Installed $LOCAL_UPLOAD to $PI:$INSTALL_DIR/upload.py"
