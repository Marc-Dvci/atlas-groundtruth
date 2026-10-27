#!/bin/sh
# Build the static site (recorded runs, no server): web/dist-static, served under $BASE (default /atlas-groundtruth/).
set -e
cd "$(dirname "$0")/.."
BASE="${BASE:-/atlas-groundtruth/}"
RUNS="${RUNS:-eval eval-open}"
rm -rf web/dist-static
(cd web && MSYS_NO_PATHCONV=1 npx vite build --mode static --outDir dist-static --base "$BASE")
.venv/Scripts/python scripts/export_static.py --out web/dist-static --runs $RUNS
