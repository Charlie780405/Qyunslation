# WT-057：壳层去重 + 高级区滚动

对应 [PLAN-057](../plans/PLAN-057-chrome-dedupe/PLAN-057-chrome-dedupe.md)。

**状态：完成**（`verify-plan-050.sh` / `verify-plan-057.sh` → `SUMMARY: PASS fail=0`，2026-09-14）

## 执行摘要

1. 入列 `docs/plans/PLAN-057-chrome-dedupe/`
2. 升级 `scripts/apply-pdf2zh-050-workbench.py`：
   - 藏 `lang-row`（`visible=False` + CSS）
   - 帮助/检查器改为 `gr.Column(visible=False)` 面板
   - `apply_adv_scroll`：把 019 的 `min(38vh, 340px)` 覆盖为 `min(55vh, 560px)`（在 left-dock 之后执行）
3. `deploy-translate-stack.sh` 后双门禁绿

## 验证

```bash
bash scripts/verify-plan-050.sh
bash scripts/verify-plan-057.sh
```

## 浏览器点验（2026-09-14，`http://127.0.0.1:7860`）

- [x] 左栏无「从…翻译 / 翻译为」；顶栏方向为唯一用户面
- [x] 无常驻「帮助 ▼ / 检查器 ▼」；点「帮助」后面板 `display:flex` 可见
- [x] 专业→展开高级：内容含 Watermark/术语表；`max-height: 560px`；左栏 `overflow-y: auto` 可滚
- [x] 强制刷新工作台正常（不白屏）

## 边界

- 补丁文件名仍为 `apply-pdf2zh-050-workbench.py`
- 不重写 019 吸底交互（只覆盖锁高）
