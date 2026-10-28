#!/bin/sh
# Copy what a live audit reads onto the Modal volume (run from the repo root): the contract records, the maps
# (OpenStreetMap waterways, PSA/NAMRIA barangays), the declared completion dates and the answer keys.
set -e
export MSYS_NO_PATHCONV=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
for d in portfolio osm admin declarations answer_key; do
  .venv/Scripts/modal volume put -f atlas-data "data/$d" "/$d"
done
