#!/bin/sh
# Build the static site (recorded runs, no server): web/dist-static, served under $BASE (default /atlas-groundtruth/).
set -e
cd "$(dirname "$0")/.."
BASE="${BASE:-/atlas-groundtruth/}"
RUNS="${RUNS:-eval eval-open bulacan blind eval-sitecheck bulacan-sitecheck blind-sitecheck}"
# the hosted live-audit server, linked from the demo header
export VITE_LIVE_URL="${VITE_LIVE_URL:-https://rgt48790--atlas-live-web.us-east.modal.run}"
rm -rf web/dist-static
(cd web && MSYS_NO_PATHCONV=1 npx vite build --mode static --outDir dist-static --base "$BASE")
.venv/Scripts/python scripts/export_static.py --out web/dist-static --runs $RUNS
