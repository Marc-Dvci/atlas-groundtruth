#!/bin/sh
# The web app for the live server: talks to the API, opens on the live page.
set -e
cd "$(dirname "$0")/../web"
rm -rf dist-live
VITE_LIVE=1 MSYS_NO_PATHCONV=1 npx vite build --outDir dist-live --base /
