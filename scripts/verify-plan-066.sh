#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

test -f frontend/src/next/AppNext.vue
test -f frontend/src/next/next.css
test -f frontend/src/next/pages/LoginPage.vue
test -f frontend/src/next/pages/WorkbenchPage.vue
test -f frontend/src/next/pages/TermbasePage.vue
test -f frontend/src/next/pages/SettingsPage.vue
test -f qyunslation/static/app/index.html

rg -q "base: '/app-assets/'" frontend/vite.config.js
rg -q "outDir: '../qyunslation/static/app'" frontend/vite.config.js
rg -q -- "--qy-primary: #005076" frontend/src/next/next.css
rg -q 'async def next_app_page' qyunslation/app.py
rg -q '"/preflights"' qyunslation/api/v1.py
rg -q '"/preferences"' qyunslation/api/v1.py

echo "PLAN-066 surface checks passed"
