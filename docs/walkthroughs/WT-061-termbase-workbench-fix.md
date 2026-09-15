# WT-061：术语工作台保存/两列/准入规则修复

> 计划：[PLAN-061](../plans/PLAN-061-termbase-workbench-fix/README.md)

## 工程验证记录

| 项目 | 结果 |
| --- | --- |
| 空单元格不再顶掉确认译法 | 已实现；专项测试通过 |
| Timer 不覆盖确认译法输入框 | 已实现；专项测试通过 |
| 桥接 HTTP 状态可诊断 | 已实现；专项测试通过 |
| `300 mg` / `Q2W` / `UK` / `OR` 不进候选 | 已实现；专项测试通过 |
| 实际/推荐译法确定性对齐 + LLM 降级 | 已实现；专项测试通过 |
| PLAN-060 evidence/bridge/ui 回归 | 已实现；专项测试通过 |
| 真实浏览器五项 | 待补 LIVE 证据 |

## 已执行本地命令

```bash
bash scripts/verify-plan-061.sh
# SUMMARY: PASS fail=0（36 项专项+回归）
python3 scripts/apply-pdf2zh-060-termbase-workbench.py   # exit 0；已写入 chosen_target 优先级
bash scripts/deploy-translate-stack.sh
# sidecar fingerprint 7542777de0fd 一致；pdf2zh + office active
```

抽取样例（非浏览器）：`tralokinumab 300 mg Q2W ... 14/18 ... UK ... OR ... NHS ... dermatitis` → 只出 `tralokinumab` / `dermatitis` / `NHS`。

## 部署记录

- GUI patch 已写入 site-packages（`chosen_target = (table_target or "").strip() or (target or "").strip()`）。
- `deploy-translate-stack.sh` 指纹只覆盖 sidecar；GUI 以 ExecStartPre 重打补丁为准。
- 重启后登录态失效，浏览器五项需重新登录后补证。

## 浏览器五项（LIVE）

1. 翻译一篇含 `300 mg` 与 `tralokinumab` 的 PDF
2. 候选列表无 `300 mg`、`14/18`、`UK`、`OR`
3. `tralokinumab` 行实际译法非占位
4. 下方输入框填确认译法后保存成功，不再提示「请先填写确认译法」
5. 「已处理」筛选可见 `approved`，刷新仍在
