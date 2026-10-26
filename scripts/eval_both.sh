#!/bin/sh
# Evaluate both model hosts on the answer key, one after the other, then compare them.
cd "$(dirname "$0")/.."
.venv/Scripts/python scripts/evaluate.py --run eval --lm meta
.venv/Scripts/python scripts/evaluate.py --run eval-open --lm open
.venv/Scripts/python scripts/evaluate.py --compare eval eval-open
