# PLAN-030ib：Manifest 可观测与下载

> 状态：**已完成**（隶属 [PLAN-030i](./PLAN-030i-delivery-closure.md)）
> 依赖：030d（`ManifestStore`）、030c（预扫 SSOT）

## 目标

用户与运维能拿到与执行链路相同的 structure manifest；扫描 tier 错误与 incomplete 状态可见，不得伪装为 0。

## 交付项

1. **JSON 下载**：预扫完成后提供「结构清单 (manifest)」下载按钮或 API；内容为 `DocumentStructureManifest.model_dump_json()`，文件名含 `source_sha256` 前缀。
2. **执行 manifest**：翻译结束后若有 execution 回写，提供 execution 变体下载或同一文件内 `execution_status` 已更新字段（与 `manifest_store.put_execution` 一致）。
3. **Tier 状态 UI**：展示 fast / semantic 层进度；Tier-3 `error`、Tier-1 截断（>20 候选）、Tier-2 部分探测（前 10）以 WARNING 呈现，字段对齐 manifest `scan_status`。
4. **语义摘要**：主区显示「N Figure、M Table」及 unnumbered 计数；物理资源数折叠为「诊断明细」。
5. **Sidecar/API  parity**：`doc_image_prescan.py` 与 GUI 预扫读同一 store 键（producer name/version 与扫描器一致）。

## 关键文件

- `qyunslation/structure/manifest_store.py`
- `scripts/doc_image_prescan.py`
- `scripts/apply-pdf2zh-prescan.py`
- `qyunslation/server/core.py`（若 REST 暴露下载）
- `tests/structure/test_plan030ib_manifest_download.py`（新建）

## 验证

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | pytest manifest 下载 round-trip | 上传 fixture → get_current → JSON schema 校验 |
| V2 | Tier error fixture | UI 模型含 non-empty error，计数不为 0 伪装 |
| V3 | ljae439 集成（可选本地） | 下载 manifest objects 编号集 = Figure 1–5, Table 1–3 |

## Out of Scope

- 新 schema 字段（除非 scan_status 展示必需且已在 030a 定义）
- 长期 manifest 归档到对象存储
