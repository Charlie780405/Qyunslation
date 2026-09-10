# PLAN-030ia：UI 画像与处理模式

> 状态：**已完成**（隶属 [PLAN-030i](./PLAN-030i-delivery-closure.md)）
> 依赖：030jd（`suggest_content_profile`）、030b（capabilities / `ProcessingMode`）

## 目标

Gradio WebUI 与 manifest 对齐：用户可见的「文档类型」= `ContentProfile`；PPTX 可选原生/图片化；产物区展示 `output_editability`。

## 交付项

1. **画像下拉**：选项覆盖 `RESEARCH_ARTICLE`、`REVIEW_ARTICLE`、`PRESENTATION`、`POSTER`、`REGULATORY`、`LETTER`、`GENERIC`（标签可中文）；默认「自动」→ 预扫后写 `profile_source=AUTO` 并展示推断结果。
2. **用户覆盖**：选择非自动时，预扫/执行传 `content_profile` 覆盖，`profile_source=USER_OVERRIDE`，manifest 保留 `profile_confidence` 与自动推断证据（只读摘要）。
3. **PPTX 模式**：当 `SourceFormat.PPTX` 且 capabilities 允许时，展示「原生可编辑 / 逐页图片化」；写入 `requested_mode`；不可选时显示 `CapabilityDecision.reason`。
4. **可编辑性提示**：预扫卡片与下载区根据 `output_editability` 显示「可编辑 Office」「图片化幻灯片」「栅格化图片」等文案。
5. **旧桥接**：`doc_profile_dropdown`（PLAN-008）映射到 nearest `ContentProfile` 或标记 deprecated；翻译模板仍可用，但不作为 SSOT。

## 关键文件

- `scripts/apply-pdf2zh-docprofile.py`（或 successor 补丁）
- `scripts/apply-pdf2zh-prescan.py`
- `scripts/doc_profile.py`（映射层，若保留）
- `qyunslation/structure/profiles.py`
- `qyunslation/structure/capabilities.py`
- `tests/structure/test_plan030ia_ui_contract.py`（新建）

## 验证

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | pytest `test_plan030ia_ui_contract.py` | 映射、mode 枚举、editability 文案 fixture 全绿 |
| V2 | `test_gui_extension_manifest.py` | 无回归 |
| V3 | 合成 PPTX manifest fixture | `requested_mode=RENDERED` → `output_editability=RASTERIZED` 提示字符串存在 |

## Out of Scope

- Manifest JSON 下载（030ib）
- 新版本钉扎（030ic）
