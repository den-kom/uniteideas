#!/usr/bin/env bash
# One-time setup on the server: install and start the auto-deploy timer for the current user.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p ~/.config/systemd/user data
cp deploy/uniteideas-deploy.service deploy/uniteideas-deploy.timer ~/.config/systemd/user/
chmod +x scripts/auto_deploy.sh
systemctl --user daemon-reload
systemctl --user enable --now uniteideas-deploy.timer
loginctl enable-linger "$USER" 2>/dev/null || echo "note: run 'sudo loginctl enable-linger $USER' so the timer keeps running after you log out"
echo "auto-deploy on. Log: $(pwd)/data/deploy.log"
systemctl --user list-timers uniteideas-deploy.timer --no-pager
