#!/usr/bin/env bash
# One-command deploy to Liara (team botyar). Reads secrets from api/.env; never prints them.
set -euo pipefail
cd "$(dirname "$0")"
TEAM="6a86b17a129b5d10d46e4dae"
APP="botyar"
ENV_FILE="api/.env"

get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }

[ -n "$(get PROD_DATABASE_URL)" ] || { echo "PROD_DATABASE_URL is empty in $ENV_FILE"; exit 1; }
[ -n "$(get OPENAI_API_KEY)" ]    || { echo "OPENAI_API_KEY is empty in $ENV_FILE"; exit 1; }
[ -n "$(get BALE_SHARED_BOT_TOKEN)" ] || { echo "BALE_SHARED_BOT_TOKEN is empty in $ENV_FILE"; exit 1; }
if [ -z "$(get JWT_SECRET)" ]; then
  [ -n "$(tail -c1 "$ENV_FILE")" ] && echo >> "$ENV_FILE"   # ensure trailing newline first
  echo "JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" >> "$ENV_FILE"
  echo "generated JWT_SECRET into $ENV_FILE"
fi

./build.sh
liara env set -a "$APP" --team-id "$TEAM" -f \
  "DATABASE_URL=$(get PROD_DATABASE_URL)" \
  "JWT_SECRET=$(get JWT_SECRET)" \
  "OPENAI_API_KEY=$(get OPENAI_API_KEY)" \
  "BALE_SHARED_BOT_TOKEN=$(get BALE_SHARED_BOT_TOKEN)" \
  "PUBLIC_BASE_URL=https://botyar.liara.run" >/dev/null
echo "env vars set"
# stage only what the image needs (keeps .venv and .env out of the upload)
STAGE="$(mktemp -d)"
cp -r api/app api/static api/Dockerfile api/requirements.txt api/liara.json "$STAGE"/
find "$STAGE" -name __pycache__ -type d -prune -exec rm -rf {} +
liara deploy --path "$STAGE" --app "$APP" --team-id "$TEAM" --platform docker --port 8000 --detach -m "deploy $(date +%F-%H%M)"
rm -rf "$STAGE"
