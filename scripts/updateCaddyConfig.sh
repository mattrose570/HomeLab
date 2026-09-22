#!/bin/bash

set -euo pipefail

REMOTE_HOST="mattrose570@new-caddy-server"
REMOTE_PATH="/home/mattrose570/Caddyfile"
LOCAL_FILE="/Volumes/SMB/Code/HomeLab/Caddy/Caddyfile"

echo "Uploading Caddyfile to $REMOTE_HOST..."

scp "$LOCAL_FILE" "$REMOTE_HOST:$REMOTE_PATH"

echo "Reloading Caddy on remote host..."

ssh "$REMOTE_HOST" "caddy fmt --overwrite && caddy reload"

echo "Done."

