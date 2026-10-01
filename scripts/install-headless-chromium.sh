#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# Install Playwright headless Chromium wrapper into ~/.local/bin (user PATH).
set -euo pipefail

PLAYWRIGHT_ROOT="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
SHELL_DIR="$(find "$PLAYWRIGHT_ROOT" -maxdepth 1 -type d -name 'chromium_headless_shell-*' 2>/dev/null | sort -V | tail -1)"
BIN="${SHELL_DIR}/chrome-headless-shell-linux64/chrome-headless-shell"
TARGET="${HOME}/.local/bin/chromium"

if [[ ! -x "$BIN" ]]; then
  echo "FAIL: headless shell not found under $PLAYWRIGHT_ROOT" >&2
  echo "Hint: python -m playwright install chromium" >&2
  exit 1
fi

mkdir -p "${HOME}/.local/bin"
cat >"$TARGET" <<EOF
#!/usr/bin/env bash
# Playwright headless Chromium wrapper (PLAN-075 browser evidence)
export PLAYWRIGHT_BROWSERS_PATH="\${PLAYWRIGHT_BROWSERS_PATH:-$PLAYWRIGHT_ROOT}"
exec "$BIN" "\$@"
EOF
chmod +x "$TARGET"

if command -v "$TARGET" >/dev/null 2>&1; then
  "$TARGET" --headless --no-sandbox --disable-gpu --version 2>/dev/null | head -1 || true
  echo "OK: installed $TARGET"
else
  echo "OK: installed $TARGET (add ~/.local/bin to PATH if needed)"
fi
