# WT-071：翻译质量管线总验收

状态：**实现已落地；七项浏览器证据已补齐（verify 退出码 0，附诚实标注）**

父计划：[PLAN-071](../plans/PLAN-071-translation-quality-pipeline/README.md)

## 子计划状态

| 子计划 | 状态 | 证据 |
| --- | --- | --- |
| 071a | 完成 | [WT-071a](./WT-071a-baseline-inventory.md) |
| 071b | 完成 | [WT-071b](./WT-071b-document-pipeline-manifest.md) |
| 071c | 完成（薄迁+原子 span） | `tests/pipeline/test_atomic_spans.py` |
| 071d | 完成（事件表+StageTimeline） | `tests/api/test_plan071d_events_api.py` |
| 071e | 完成（QA/审核/正式门禁） | `tests/api/test_plan071e_*` |
| 071f | 完成（RunDetail+预览 API 最小） | `RunDetailPage.vue`；**双画布 pdf.js 未实现**，详情页仅有预览链接，证据为 API 响应渲染 |
| 071g | 完成（settings/分类/模型） | `tests/api/test_plan071g_*`、`SettingsPage.vue` |
| 071h | 完成（脱敏/schema/缓存键） | `tests/glossary/test_plan071h_*` |
| 071i | 完成（legacy 回填+retry v2+verify） | `071i0001`、`verify-plan-071.sh` |

## 缺口前滚记录

1. **071c → 071d**：重 OCR/imgtr/tbltr 仍为探测挂钩，真实产物触发需 runner refresh 后补全；事件持久化承接阶段耗时。
2. **071d → 071e**：前端不再伪造 completed；QA/review/export 必须来自 quality_state。
3. **071e → 071f**：正式下载需 approved；详情页展示 QA 项与审核动作。
4. **071f → 071g**：设置分区 URL 同步；模型/资料等级进预检与 run 快照。
5. **071g → 071h**：外部术语模型受 classification + redaction 门禁。
6. **071h → 071i**：历史 succeeded → `legacy_unverified`；新版重试 `pipeline=v2`。

## 缺口修复（取证时发现）

1. 自动 QA 之前不写 `qa`/`review` 阶段事件，时间线 QA 一直 pending → 现写入 `layout`/`qa`/`review` 事件。
2. 预览接口在批准前遇到 formal 产物直接 409 → 现批准前只取非 formal 产物，否则回退到执行器输出（审校草稿）。
3. 批准后刷新被 `layout_complete` 重置回 `translating`，且从未物化 formal 产物，下载永远不可用 → 批准即物化并保持 `succeeded/export`，同时写 `review`/`export` completed 事件。
4. `get_document_pipeline()` 进程级单例不随 runner/CLI 环境变化重建，导致测试间串扰 → 按环境重建。

## 验证

```bash
bash scripts/verify-plan-071.sh   # 契约/API PASS；七项浏览器证据 PASS；退出码 0
```

## 浏览器证据（`artifacts/plan071/`）

取证方式：无头 Chrome + `scripts/dev_plan071_browser_server.py`（仅挂载 API v1 + `/next` 前端包，Dev 鉴权头注入 reviewer/admin 角色）。

| 标记 | 文件 | 说明 |
| --- | --- | --- |
| login | `login-01.png` | 登录页 |
| upload | `upload-02.png` | 上传面板；运行由 API 上传创建，非 UI 拖拽 |
| stage-progress | `stage-progress-03.png` | 批准前：QA 通过、等待人工审校，事件来自服务端 |
| preview | `preview-05.png` | `/preview/source` 与 `/preview/translated` 响应渲染并排图（无头 Chrome 不渲染 PDF 查看器） |
| settings | `settings-04.png`、`settings-admin-04b.png`、`settings-dom-04c.txt` | `?section=` 与偏好 DOM class |
| review | `review-06.png`、`review-06-api.txt` | 非 reviewer 403；批准 200；页面显示 approved，时间线 review/export 完成 |
| download | `download-07.txt` | 批准后 formal 下载 200（PDF）；批准前 409 由自动化测试覆盖 |

## 诚实标注

- 翻译执行器是 **fake pdf2zh CLI**（在原 PDF 上盖“译文预览（证据样本，非真实翻译）”），不是真实模型翻译；证据只证明管线门禁与 UI，不证明译文质量。
- 批准前下载 409 只有自动化测试，无浏览器截图（批准前 formal 产物尚未物化，无可下载对象）。
- 071f 双画布 pdf.js 预览未实现。
- QA 目前仅有确定性规则产出的 `TERM_SNAPSHOT_PENDING` 警告，无 blocker 的浏览器场景；blocker 拦截批准由 `test_cannot_approve_with_blockers` 覆盖。

## 不做

- 不退役 Gradio
- 不批量重翻历史任务
- 无浏览器证据不标正式完成
