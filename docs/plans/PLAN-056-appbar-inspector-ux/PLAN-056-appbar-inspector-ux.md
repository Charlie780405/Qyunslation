# PLAN-056：应用栏与检查器可见性收口

> 状态：**完成**
> 日期：2026-09-13
> 依赖：PLAN-050（050a–g 已关）；不占用 050h
> 验收门：`bash scripts/verify-plan-056.sh`
> Walkthrough：[WT-056](../../walkthroughs/WT-056-appbar-inspector-ux.md)

## 一句话

修 Gradio 顶栏：紧凑方向/模式开关、帮助与检查器在应用栏下可见（去掉 `translateX` 抽屉），并与左栏 `lang_from`/`lang_to` 双向同步。

## 为何新号

PLAN-050 已关闭；Cursor 草稿「050 顶栏改版」撞号。索引下一空号为 **056**（055 已占用）。

## 施工面

| 项 | 值 |
| --- | --- |
| UI | `pdf2zh_next --gui --server-port 7860` |
| 补丁 | `scripts/apply-pdf2zh-050-workbench.py`（文件名保留；脚本头标注 050+056） |
| 部署 | `bash scripts/deploy-translate-stack.sh` |
| 契约 | `docs/contracts/ui-runtime-050.md`（056 更新检查器锚点） |

## 子计划

| ID | 交付 |
| --- | --- |
| [056a](./PLAN-056a-appbar-direction.md) | 紧凑应用栏 + `qy_dir` ↔ `lang_from`/`lang_to` |
| [056b](./PLAN-056b-inspector-help.md) | 去掉抽屉位移；帮助/检查器 Accordion |
| [056c](./PLAN-056c-verify-gate.md) | verify-056 + 部署 + 浏览器点验 |

## Out of Scope

- Vue `frontend/`、第二套生产前端
- 050e 级对象单元格/OCR 真编辑器
- PLAN-055 alembic / Authentik / Caddy
- 金标翻译矩阵（仍归 051）

## 后续

去重双入口与高级区滚动见 **[PLAN-057](../PLAN-057-chrome-dedupe/PLAN-057-chrome-dedupe.md)**。

## 完成定义

- [x] 纲领 + 056a/b/c + README；plans 索引有 056 行
- [x] 顶栏无费解文案；英→中/中→英与左栏同步
- [x] 检查器/帮助点开后在视口内可见
- [x] `verify-plan-050.sh` 与 `verify-plan-056.sh` PASS；强制刷新不白屏
