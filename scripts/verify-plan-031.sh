#!/usr/bin/env bash
# PLAN-031 验收：派生作品收口（Private / NOTICE / 用户可见品牌 / remote）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
pass=0; fail=0
ok() { echo "  ok    $*"; pass=$((pass+1)); }
bad() { echo "  FAIL  $*"; fail=$((fail+1)); }

echo "== 1. 许可与出处 =="
[[ -f "$ROOT/LICENSE" ]] && ok "LICENSE" || bad "LICENSE"
[[ -f "$ROOT/NOTICE.md" ]] && ok "NOTICE.md" || bad "NOTICE.md"
grep -q 'xunbu/docutranslate' "$ROOT/NOTICE.md" && ok "NOTICE 上游 URL" || bad "NOTICE 上游 URL"
grep -q 'MPL-2.0' "$ROOT/NOTICE.md" && ok "NOTICE MPL-2.0" || bad "NOTICE MPL-2.0"
grep -q '导入的 git 历史' "$ROOT/NOTICE.md" && ok "NOTICE 解释 Contributors" || bad "NOTICE Contributors"

echo "== 2. 包名不变量 =="
grep -q '^name = "qyunslation"' "$ROOT/pyproject.toml" && ok "pyproject name" || bad "pyproject name"
grep -q 'qyunslation = "qyunslation.cli:main"' "$ROOT/pyproject.toml" && ok "CLI entry" || bad "CLI entry"

echo "== 3. 根目录不再以 DocuTranslate 为产品名 =="
[[ ! -e "$ROOT/DocuTranslate.png" && ! -e "$ROOT/DocuTranslate.ico" && ! -e "$ROOT/DocuTranslate.icns" ]] \
  && ok "根目录无 DocuTranslate 图标" || bad "根目录仍有 DocuTranslate 图标"
grep -q '<h1 align="center">Qyunslation</h1>' "$ROOT/README.md" && ok "README 标题" || bad "README 标题"
grep -q '<h1 align="center">Qyunslation</h1>' "$ROOT/README_ZH.md" && ok "README_ZH 标题" || bad "README_ZH 标题"
! grep -q '<h1 align="center">DocuTranslate</h1>' "$ROOT/README.md" "$ROOT/README_ZH.md" \
  && ok "README 无上游 H1" || bad "README 仍有上游 H1"

echo "== 4. 用户可见文案 =="
grep -q '欢迎使用 Qyunslation' "$ROOT/qyunslation/cli.py" && ok "cli 欢迎语" || bad "cli 欢迎语"
! grep -q '欢迎使用 DocuTranslate' "$ROOT/qyunslation/cli.py" && ok "cli 无旧欢迎语" || bad "cli 旧欢迎语"
grep -q '正在启动 Qyunslation WebUI' "$ROOT/qyunslation/app.py" && ok "app 启动语" || bad "app 启动语"
grep -q 'Powered by Qyunslation' "$ROOT/qyunslation/template/markdown.html" && ok "markdown 页脚" || bad "markdown 页脚"
! grep -q 'Powered by DocuTranslate' "$ROOT/qyunslation/template/markdown.html" && ok "页脚无旧品牌" || bad "页脚旧品牌"
grep -q '"pageTitle": "荃信翻译 · Qyunslation"' "$ROOT/qyunslation/static/i18n/zh.json" && ok "i18n zh pageTitle" || bad "i18n zh pageTitle"
grep -q '"pageTitle": "荃信翻译 · Qyunslation"' "$ROOT/frontend/public/i18n/zh.json" && ok "frontend i18n zh" || bad "frontend i18n zh"
! grep -q 'xunbu/docutranslate/pulls' "$ROOT/frontend/src/components/modals/ContributorsContent.vue" \
  && ok "贡献弹窗无上游 PR" || bad "贡献弹窗仍指向上游"
grep -q '"name": "qyunslation-frontend"' "$ROOT/frontend/package.json" && ok "frontend 包名" || bad "frontend 包名"
grep -q 'LABEL authors="Charlie780405"' "$ROOT/Dockerfile" && ok "Dockerfile LABEL" || bad "Dockerfile LABEL"
! grep -q 'xunbu/docutranslate:latest' "$ROOT/Dockerfile" && ok "Dockerfile 无上游镜像名" || bad "Dockerfile 上游镜像名"
grep -q 'Qyunslation 环境变量' "$ROOT/.env.example" && ok ".env.example 文件头" || bad ".env.example 文件头"
grep -q 'name=f.Qyunslation' "$ROOT/lite.spec" && ok "lite.spec 产出名" || bad "lite.spec 产出名"

echo "== 5. remote =="
if git -C "$ROOT" remote get-url origin >/tmp/qy031-origin.txt 2>/dev/null; then
  grep -q 'Charlie780405/Qyunslation' /tmp/qy031-origin.txt && ok "origin=本仓" || bad "origin=$(cat /tmp/qy031-origin.txt)"
else
  bad "origin 不存在"
fi
if git -C "$ROOT" remote get-url upstream >/tmp/qy031-up.txt 2>/dev/null; then
  grep -q 'xunbu/docutranslate' /tmp/qy031-up.txt && ok "upstream=DocuTranslate" || bad "upstream=$(cat /tmp/qy031-up.txt)"
else
  bad "upstream 不存在"
fi

echo "== 6. GitHub（可选） =="
if command -v gh >/dev/null 2>&1; then
  vis=$(gh repo view Charlie780405/Qyunslation --json visibility,description --jq '"\(.visibility)|\(.description)"' 2>/tmp/qy031-gh.err || true)
  if [[ "$vis" == PRIVATE* ]]; then
    ok "仓库 Private"
  else
    bad "仓库可见性 $vis"
    cat /tmp/qy031-gh.err || true
  fi
  echo "$vis" | grep -q '派生' && ok "About 含派生" || bad "About 无派生说明"
else
  echo "  skip  gh 不可用"
fi

echo "== 7. 烟囱 =="
PY=""
for c in "$ROOT/.venv/bin/python" /home/dev/qyunslation/.venv/bin/python python3; do
  [[ -x "$c" || "$c" == python3 ]] && PY="$c" && break
done
if [[ -n "$PY" ]]; then
  PYTHONPATH="$ROOT" "$PY" -c "import qyunslation, qyunslation.app; print('import_ok', qyunslation.__version__)" \
    >/tmp/qy031-imp.txt 2>&1 && ok "import qyunslation.app $(tail -1 /tmp/qy031-imp.txt)" || {
      bad "import qyunslation.app"; cat /tmp/qy031-imp.txt
    }
  PYTHONPATH="$ROOT" "$PY" -m qyunslation.cli -h >/tmp/qy031-h.txt 2>&1 || true
  if grep -q 'Qyunslation' /tmp/qy031-h.txt; then
    ok "qyunslation -h 品牌"
  else
    # argparse 无参走欢迎语；-h 走 description
    PYTHONPATH="$ROOT" "$PY" -m qyunslation.cli >/tmp/qy031-cli.txt 2>&1 || true
    grep -q 'Qyunslation' /tmp/qy031-cli.txt && ok "qyunslation 欢迎语" || bad "qyunslation CLI 品牌"
  fi
else
  echo "  skip  无可用 python"
fi

echo
echo "PASS=$pass FAIL=$fail"
[[ "$fail" -eq 0 ]]
