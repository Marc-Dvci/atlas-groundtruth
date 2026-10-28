#!/bin/sh
# Create the Modal secret the live server reads: only the keys an audit needs, plus an owner token that unlocks live
# audits until they are opened to the public (ATLAS_LIVE_OPEN=1 in deploy/modal_app.py). Run from the repo root.
set -e
export MSYS_NO_PATHCONV=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
grep -q "^ATLAS_LIVE_TOKEN=" .env || printf 'ATLAS_LIVE_TOKEN=%s\n' "$(.venv/Scripts/python -c 'import secrets; print(secrets.token_urlsafe(18))')" >> .env
tmp="$(mktemp)"
grep -E "^(MODEL_API_KEY|MAPILLARY_TOKEN|BASETEN_API_KEY|BASETEN_MODEL|ATLAS_LIVE_TOKEN)=" .env > "$tmp"
.venv/Scripts/modal secret create atlas-keys --from-dotenv "$tmp" --force
rm -f "$tmp"
echo "secret atlas-keys created; your owner token is ATLAS_LIVE_TOKEN in .env"
