# WT-074：作者/单位原文保护、术语闭环与乱码门禁

> 状态：**工程闭环；legacy 真件 QA 待重跑**

## 执行摘要

PLAN-074 在 `/next` PDF 文献/Poster 路径上保护作者元数据、结构化抽取专业术语并在正式批准前强制闭环，同时阻断乱码与 IL 标签残留。单位人工审校为历史行为，当前英文单位保留原文。

## 变更明细

| 区域 | 交付 |
| --- | --- |
| 074a | `frontmatter.py` 作者/单位分类；BabelDOC 作者与英文单位块跳过 LLM |
| 074b | 历史实现：affiliation 审校 API；`apply-corrections` 新一代；`translation_trace` 精确写回（当前已停用） |
| 074c | `term_extract` 结构化补充；术语审校面板；历史 `formal_gate` 曾包含单位确认 |
| 074d | `text_sanitize` 扩展；单/双语 PDF 阻断；`_QY_074_POSTPROCESS` 钩子 |

## 验证

```bash
bash scripts/verify-plan-074.sh
bash scripts/plan074-live-regression.py
```

- 后端/API/迁移/patch — PASS（58 tests）
- 前端 Vitest + axe + build — PASS
- Dupilumab 真件 — **BLOCKED**（legacy dual PDF 仍有 `IL_MARKUP_LEAK`/`TEXT_ENCODING_ARTIFACT`；术语金标 PASS）

## 生产发布（2026-10-02，PLAN-075a）

| 步骤 | 结果 |
| --- | --- |
| 备份 | `/home/dev/pdf2zh/backups/qyunslation-pre-074a-20261001T205548Z.dump` |
| Alembic | `073a0001` → **`074a0001`** |
| Git | `main` @ `6915de3`（074 六提交 + verify 脚本） |
| 部署 | sidecar 指纹 `7542777de0fd`；`affiliation-segments`/`apply-corrections` → **401** |
| 部署门禁 | PLAN-075b `deploy_gate.py` pre/post 检查 |

## 后续

用 PLAN-074 流水线重跑 Dupilumab Poster，使 live regression QA 段从 BLOCKED 转为 PASS。

## 当前行为变更（2026-10-19）

- 英文研究单位段与已识别的英文作者姓名在翻译阶段按原文保留；这些原文不会被英文残留 QA 误报。
- QA 不再创建新的单位审核段；旧单位记录不再出现在 `/next`，也不再阻挡正式稿批准。
- 中译英时，文档中已存在的英文单位/姓名原文会原样保留；没有英文原文的中文名称仍按原翻译流程处理。

### 生产发布

- 变更提交：`a672262`（`main`，已推送 `origin/main`）。
- 部署：`scripts/deploy-translate-stack.sh` — **PASS**；migration aligned、frontend build fresh、API routes registered；`pdf2zh.service` 与 `qyunslation-office.service` 均 active；sidecar 本地/远端指纹一致（`7542777de0fd`）。
- 健康检查：本机 GUI `/`、公网 `/next/`、公网 `/api/v1/health`、带认证的 sidecar health 均 HTTP 200。公网页面引用新资源 `index-BiX4OdPw.js`、`index-CxUYWDDV.css`、`index-legacy-OO8704Kx.js`。
- 验证：Python `py_compile`、前端 `vue-tsc --noEmit`、Vite production build — **PASS**。pytest/Vitest 未运行；浏览器视觉验收 **BLOCKED**（当前会话没有 Chrome DevTools/浏览器自动化工具）。
- 术语库闭环：本次未修改术语候选批准或复用行为，未执行新的生产术语裁决。
