#!/usr/bin/env bash
# PLAN-030e Task 1: install LibreOffice for legacy .doc/.ppt normalization.
set -euo pipefail

if command -v soffice >/dev/null 2>&1 || command -v libreoffice >/dev/null 2>&1; then
  echo "LibreOffice already available: $(command -v soffice || command -v libreoffice)"
  exit 0
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "apt-get not found; install LibreOffice manually and ensure soffice is on PATH" >&2
  exit 1
fi

# Server/Vultr: use the nogui stack only. Mixing libreoffice-core-nogui with
# libreoffice-writer/impress (GUI) pulls libreoffice-core and apt conflicts.
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  libreoffice-core-nogui \
  libreoffice-writer-nogui \
  libreoffice-impress-nogui

command -v soffice >/dev/null 2>&1 || command -v libreoffice >/dev/null 2>&1
echo "LibreOffice installed: $(command -v soffice || command -v libreoffice)"
