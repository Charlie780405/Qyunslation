# WT-071：翻译质量管线总验收

状态：**工程闭环完成（代码、自动化、八项浏览器证据，`verify-plan-071.sh` 退出码 0）；真实环境类发布门禁仍为 BLOCKED，见“发布门禁”表**

父计划：[PLAN-071](../plans/PLAN-071-translation-quality-pipeline/README.md)

## 子计划状态

| 子计划 | 状态 | 证据 |
| --- | --- | --- |
| 071a | 完成 | [WT-071a](./WT-071a-baseline-inventory.md) |
| 071b | 完成 | [WT-071b](./WT-071b-document-pipeline-manifest.md) |
| 071c | **部分**：薄迁 + 原子 span 完成；table_figure/layout 后处理阶段仍 `enabled=False`，logo/imgtr/tbltr 未接入管线 | `tests/pipeline/test_atomic_spans.py` |
| 071d | 完成：事件表、`emit_stage_*`、单元进度持久化、旧 generation 拒写、resume 跳过 | `tests/persist/test_plan071d_stage_events.py`、`tests/api/test_plan071d_events_api.py` |
| 071e | 完成：真实 PDF 检查（页数/logo/邮箱/IND/剂量/URL/空译/序号/回退/未翻译正文）、审核门禁、正式下载 | `tests/pipeline/test_plan071e_pdf_inspect.py`、`tests/api/test_plan071e_*` |
| 071f | 完成：双画布 pdf.js、对象检查器、URL 同步、Range/416、租户隔离、图片/Office 预览（Office 依赖 soffice） | `tests/api/test_plan071f_*`、`frontend/src/next/__tests__/`、`dual-canvas-08.png` |
| 071g | 完成：偏好/分类/模型 + 租户策略持久化与锁定（403 `PREFERENCE_LOCKED`）、生效来源 | `tests/api/test_plan071g_*`、迁移 `071g0002` |
| 071h | 完成：脱敏/schema/缓存键、run 级术语快照（哈希）驱动 QA、查找顺序、外发脱敏、高风险批准 | `tests/glossary/test_plan071h_*`、`tests/pipeline/test_plan071h_term_snapshot.py` |
| 071i | 完成：legacy 回填、retry v2、按租户灰度并冻结进 run 快照、模型/外发/补丁指纹快照 | `tests/api/test_plan071i_*`、`tests/persist/test_plan071_migrations.py` |

## 缺口前滚记录

1. **071c → 071d**：重 OCR/imgtr/tbltr 仍为探测挂钩；事件持久化承接阶段耗时。
2. **071d → 071e**：前端不再伪造 completed；QA/review/export 必须来自 quality_state。
3. **071e → 071f**：正式下载需 approved；详情页展示 QA 项与审核动作。
4. **071f → 071g**：设置分区 URL 同步；模型/资料等级进预检与 run 快照。
5. **071g → 071h**：外部术语模型受 classification + redaction 门禁。
6. **071h → 071i**：历史 succeeded → `legacy_unverified`；新版重试 `pipeline=v2`。

## 缺口修复（取证与审计时发现）

1. 自动 QA 之前不写 `qa`/`review` 阶段事件 → 现写入 `layout`/`qa`/`review` 事件。
2. 预览接口批准前遇 formal 产物直接 409 → 批准前取非 formal 产物，否则回退执行器输出。
3. 批准后刷新被重置回 `translating`，且从未物化 formal 产物 → 批准即物化并保持 `succeeded/export`。
4. `get_document_pipeline()` 单例不随环境变化重建 → 按环境键重建。
5. **QA 原先只有占位警告，未读 PDF**：未翻译副本也能 review_ready → 现读取源/译文 PDF，blocker 级问题使 run 进入 `qa_blocked`，批准返回 409。
6. 术语快照原为 `snapshot_pending` 占位 → 现由 run 级哈希快照驱动 forbidden/high-risk/missing 检查；后续词库变更不改写已有 run 快照。
7. 预览无租户/Range/图片/Office 处理 → 补齐，Office 缺 soffice 时返回 501 `OFFICE_PREVIEW_UNAVAILABLE`，不伪造。
8. 管线模式依赖进程级环境变量，retry 会改全局 env → 改为 run 快照冻结 `pipeline`，历史无该键视为 legacy。
9. 偏好锁定仅有前端展示 → 后端 `tenant_policy` 持久化，写入被锁字段返回 403。

## 验证

```bash
bash scripts/verify-plan-071.sh   # 契约/API/迁移/vitest 全 PASS；八项浏览器证据 PASS；退出码 0
```

覆盖：`tests/pipeline` 与 `tests/api` 的 071 用例、`tests/persist` 真实 alembic 升降级与 legacy 回填、`tests/glossary/test_plan071h_*`、`frontend` vitest（21 用例）。

## 浏览器证据（`artifacts/plan071/`）

取证方式：无头 Chrome + `scripts/dev_plan071_browser_server.py`（仅挂载 API v1 + `/next` 前端包，Dev 鉴权头注入 reviewer/admin 角色）。

| 标记 | 文件 | 说明 |
| --- | --- | --- |
| login | `login-01.png` | 登录页 |
| upload | `upload-02.png` | 上传面板；运行由 API 上传创建，非 UI 拖拽 |
| stage-progress | `stage-progress-03.png` | 批准前：QA 通过、等待人工审校，事件来自服务端 |
| preview | `preview-05.png` | `/preview/source` 与 `/preview/translated` 响应渲染并排图 |
| settings | `settings-04.png`、`settings-admin-04b.png`、`settings-dom-04c.txt` | `?section=` 与偏好 DOM class |
| review | `review-06.png`、`review-06-api.txt` | 非 reviewer 403；批准 200；页面 approved |
| download | `download-07.txt` | 批准后 formal 下载 200（PDF）；批准前 409 由自动化测试覆盖 |
| dual-canvas | `dual-canvas-08.png` | 双画布 pdf.js 渲染与对象检查器 |

## 发布门禁（诚实状态）

| 门禁 | 状态 | 原因 |
| --- | --- | --- |
| 自动化 + 迁移 + vitest + 浏览器证据 | PASS | `verify-plan-071.sh` 退出码 0 |
| 071c 真实后处理（table_figure / layout / logo / imgtr / tbltr 接入） | **BLOCKED** | 阶段仍 `enabled=False`，需真实 pdf2zh_next 与样本联调 |
| FDA 20 页真实样本端到端 | **BLOCKED** | 无样本与真实翻译引擎 |
| 表格/图片密集 PDF 样本 | **BLOCKED** | 同上 |
| DOCX/PPTX/图片真实样本 | **BLOCKED** | 缺真实样本；Office 预览需 soffice |
| Qwen vs DeepSeek 盲测 | **BLOCKED** | 无外部模型访问与评审集 |
| DeepSeek 版本探测 | **BLOCKED** | `reported_version=None`、`version_pinned=False`，快照如实记录“未固定” |
| soffice / pdf2zh_next | **不可用** | 本环境未安装 |

## 诚实标注

- 翻译执行器是 **fake pdf2zh CLI**（在原 PDF 上盖“译文预览（证据样本，非真实翻译）”），不是真实模型翻译；证据证明管线门禁与 UI，不证明译文质量。
- 批准前下载 409 只有自动化测试，无浏览器截图。
- 预览证据在无头 Chrome 中为响应渲染图，非内嵌 PDF 查看器（双画布另有 pdf.js 截图）。
- 外发脱敏失败时当前是 **fail-closed**（跳过外部调用），未回退内部 Qwen 提供方。
- `tests/ui/test_runtime_surface_050.py` 有 2 个既有失败（硬编码 `/home/dev/qyunslation` 路径），`tests/glossary` 与 `test_figure_data_mark` 因缺 `cv2` 收集失败，均与 071 无关。

## 不做

- 不退役 Gradio
- 不批量重翻历史任务
- 无真实环境证据不标“发布完成”
