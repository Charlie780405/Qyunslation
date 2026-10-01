# WT-071：翻译质量管线总验收

状态：**实现已落地；浏览器证据 BLOCKED**

父计划：[PLAN-071](../plans/PLAN-071-translation-quality-pipeline/README.md)

## 子计划状态

| 子计划 | 状态 | 证据 |
| --- | --- | --- |
| 071a | 完成 | [WT-071a](./WT-071a-baseline-inventory.md) |
| 071b | 完成 | [WT-071b](./WT-071b-document-pipeline-manifest.md) |
| 071c | 完成（薄迁+原子 span） | `tests/pipeline/test_atomic_spans.py` |
| 071d | 完成（事件表+StageTimeline） | `tests/api/test_plan071d_events_api.py` |
| 071e | 完成（QA/审核/正式门禁） | `tests/api/test_plan071e_*` |
| 071f | 完成（RunDetail+预览 API 最小） | `RunDetailPage.vue`；双画布 pdf.js 待浏览器证据 |
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

## 验证

```bash
bash scripts/verify-plan-071.sh
```

本环境预期：契约/API **PASS**；Chrome DevTools 七项证据目录 `artifacts/plan071/` 缺失 → **BLOCKED**（允许，不得假绿标完成）。

## 浏览器证据清单（发布前必补）

| 标记 | 说明 |
| --- | --- |
| login | 登录与 workbench_v2 能力 |
| upload | 预检上传 |
| stage-progress | StageTimeline 读 events |
| preview | `/preview/source|translated` |
| settings | `?section=` 与 reduceMotion DOM |
| review | review-decision approve |
| download | formal 未批准 409 / 批准后可下 |

## 不做

- 不退役 Gradio
- 不批量重翻历史任务
- 无浏览器证据不标正式完成
