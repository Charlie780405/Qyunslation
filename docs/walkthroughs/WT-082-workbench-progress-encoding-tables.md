# WT-082：工作台进度、预检状态、乱码误报与表格混乱

## 切片

| 切片 | 内容 | 关键改动 |
| --- | --- | --- |
| S1 | 放弃本版本 → `/workbench` + 一次性提示 | `RunDetailPage.vue`、`listView.notice` |
| S2 | 任务创建后重置上传区；进度只在任务卡 | `WorkbenchPage.vue` |
| S3 | PTY + Rich 进度解析；轮询签名含 `progress_message` | `runner.py`、`WorkbenchPage.vue` |
| S4 | 空格字形乱码降级 + ToUnicode 修复 | `text_sanitize.py`、`pdf_space_cmap.py`、`pdf_inspect.py` |
| S5 | 表格后处理接入 + `TABLE_TEXT_OVERLAP` | `postprocess.py`、`runner.py`、`pdf_inspect.py` |

## 开关

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `QYUNSLATION_RUNNER_PTY` | `1` | CLI 走 PTY 以获得 Rich 实时进度 |
| `QYUNSLATION_FIX_SPACE_CMAP` | `1` | 给 ToUnicode 补 CID 3→空格 |
| `QYUNSLATION_TABLE_POSTPROCESS` | `literature` | `off` / `literature` / `normalize` / `translate` |

## S5 基线（CM512 样本，只读）

样本：`09-LIT-2026-CM512-Trial` generation-1 mono PDF。

| 项 | 结果 |
| --- | --- |
| 文档类型 | `RESEARCH_ARTICLE` |
| 源文表数 | 4（页 5/6/7） |
| 页 5 文字框重叠对 | 56 |
| 页 6 文字框重叠对 | 58 |
| 页 5/6 字号种类 | 12 / 10（目标 ≤3） |

结论：BabelDOC 表区按段落流排版，表头/数值重叠；后处理已接入 normalize/translate 降级链，QA 对重叠表区出 `TABLE_TEXT_OVERLAP` 阻断。

## 验收边界

- 浏览器视觉 / axe：无隔离 Chrome DevTools MCP 时标 BLOCKED，不拿 HTTP 冒充。
- 回滚：关上述开关或回退静态资源；无数据库迁移。

## 部署证据（2026-10-20）

- Commit：`c12900b1`（`feat(PLAN-082): fix workbench progress, stale preflight, encoding false positives, and table QA`）
- 分支：`feat/PLAN-081-translation-admission-and-service-api` → 已推送 `origin`
- 部署：`bash scripts/deploy-translate-stack.sh` → PASS（pre/post gates、fingerprint 一致）
- 服务：`qyunslation-office.service` / `pdf2zh.service` active
- 浏览器视觉验收：BLOCKED（无隔离 Chrome DevTools MCP）
