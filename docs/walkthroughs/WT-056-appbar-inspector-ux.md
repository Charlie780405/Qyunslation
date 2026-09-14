# WT-056：应用栏方向开关 + 检查器可见性

对应 [PLAN-056](../plans/PLAN-056-appbar-inspector-ux/PLAN-056-appbar-inspector-ux.md)。

**状态：完成**（`verify-plan-050.sh` / `verify-plan-056.sh` → `SUMMARY: PASS fail=0`，2026-09-13）

## 执行摘要

1. 入列 `docs/plans/PLAN-056-appbar-inspector-ux/`（不重开 050）
2. 升级 `scripts/apply-pdf2zh-050-workbench.py`：紧凑顶栏、`qy_dir` 双向同步、检查器/帮助 Accordion
3. 去掉 `translateX(100%)` 抽屉 CSS；禁止 `js=`；`re.sub` 用 lambda 避免 `\n` 被吃掉
4. `bash scripts/deploy-translate-stack.sh` 后双门禁绿

## 验证

```bash
bash scripts/verify-plan-050.sh
bash scripts/verify-plan-056.sh
```

## 浏览器点验（2026-09-13，`http://127.0.0.1:7860`）

- [x] 顶栏：就绪｜英→中/中→英｜快速/专业｜帮助｜检查器
- [x] 点「检查器」在应用栏下可见正文（`transform: none`，非视口外）
- [x] 「中→英」→ 左栏 `Simplified Chinese` / `English`；⇄ 后顶栏回到「英→中」
- [x] 帮助可开合；强制刷新后工作台正常（不白屏）

## 边界

- 补丁文件名仍为 `apply-pdf2zh-050-workbench.py`
- 不做 050e 级对象编辑器
