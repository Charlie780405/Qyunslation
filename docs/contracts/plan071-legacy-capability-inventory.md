# PLAN-071 旧能力盘点矩阵

> 父计划：[PLAN-071](../plans/PLAN-071-translation-quality-pipeline/README.md)
> 子计划：[071a](../plans/PLAN-071-translation-quality-pipeline/PLAN-071a-baseline-inventory.md)
> 补丁顺序 SSOT：[`pdf2zh-patch-order.md`](./pdf2zh-patch-order.md)

分类：

| 码 | 含义 |
| --- | --- |
| **A** | 可直接迁移的应用逻辑 → `qyunslation/pipeline/stages/*` |
| **B** | 仅 Gradio/UI |
| **C** | 上游 pdf2zh_next/BabelDOC 已大致覆盖（需验证后标 covered） |
| **D** | 运行时 monkey patch 第三方内部（指纹登记；071i 前评估去留） |

## 1. 质量相关钩子（优先迁移）

| ID | 能力 | 注入/入口 | 逻辑模块 | 分类 | 迁移目标 |
| --- | --- | --- | --- | --- | --- |
| Q-01 | 文档画像 detect/apply | `apply-pdf2zh-docprofile.py` | `scripts/doc_profile.py` | **A** | `pipeline/stages/doc_profile.py`（仅配置，不含 typesetting patch） |
| Q-02 | letter/lit/reg typesetting monkey patch | 同上 `patch_*_typesetting` | `scripts/doc_profile.py` | **D** | 指纹登记；不进 DocumentPipeline |
| Q-03 | 专名 harvest + glossary 拼接 | docprofile 路径 | `scripts/proper_nouns.py` | **A** | `pipeline/stages/proper_nouns.py` |
| Q-04 | HPD OCR 前置 | `apply-pdf2zh-hpd.py` | `scripts/hpd_ocr.py` | **A** | `pipeline/stages/ocr_hpd.py`（runner 已有弱重试，应升为译前阶段） |
| Q-05 | letter 旁路重绘 | docprofile `_qy_letter_reflow` | `scripts/letter_pipeline.py` + `letter_layout.py` + `kv_reinsert.py` | **A** | `pipeline/stages/letter_reflow.py` |
| Q-06 | `^{th}` 清洗 | letter_layout `clean_text` | `scripts/letter_layout.py` | **A** | 保留防御 + `pipeline/atomic_spans.py` |
| Q-07 | Logo/印章回填 | `_qy_graphic_reinsert` | `scripts/graphic_reinsert.py` + `graphic_regions.py` | **A** | `pipeline/stages/preserve_graphics.py` |
| Q-08 | 嵌图后处理 imgtr | `apply-pdf2zh-docimg.py` `_qy_imgtr_post` | `scripts/pdf_image_translate.py` → `extensions/image_translate.py` | **A** | `pipeline/stages/image_overlay.py` |
| Q-09 | 表格后处理 tbltr | 同 docimg `_qy_tbltr` | `scripts/pdf_table_translate.py` + `structure/table_*` | **A** | `pipeline/stages/table_translate.py` |
| Q-10 | figure inventory / Manifest 区域 | imgtr 内 | `structure/scan_pdf.py` `ManifestStore` | **A** | 071b Manifest 2.0 structure 阶段 |
| Q-11 | mono fallback dual | ocr-base / docimg | `apply-pdf2zh-ocr-base.py` | **A**/部分 **C** | 执行器产物归一小兜底 |
| Q-12 | Office/图片 sidecar 路由 | `apply-pdf2zh-office-route.py` | `:8010` `app.py` + `workflow/*` | **A**（业务）+ **B**（GUI 壳） | `pipeline/executors/office.py` / `image.py` |
| Q-13 | 术语桥抽候选 | `apply-pdf2zh-060-termbase-workbench.py` | `workbench/gui_client.py` / bridge | **A** + **B** | 071h；UI 用 Vue |

## 2. BabelDOC / site-packages monkey patch（D）

| ID | 脚本 | 标记 | 目标文件（典型） | 分类 | 说明 |
| --- | --- | --- | --- | --- | --- |
| D-01 | `apply-pdf2zh-042b-short-label.py` | `_qy_042b_short_label_direct` | babeldoc IL translator | **D**+**A** glossary | 监管短标签直替 |
| D-02 | `apply-pdf2zh-046b-para-merge.py` | `_QY_046B_PARA_MERGE` | paragraph_finder/typesetting | **D** | 文献段落合并 |
| D-03 | `apply-pdf2zh-047d-para-layout.py` | `_QY_047D_PARA_LAYOUT` | typesetting | **D** | 段落布局守卫 |
| D-04 | `apply-pdf2zh-047c-no-drop.py` | `_QY_047C_NO_DROP` | `pdf_creater.py` | **D** | 禁静默丢段 |
| D-05 | `apply-pdf2zh-fidelity-033h.py` | `_QY_033H_PRESERVE` | IL translator | **D** | references preserve |
| D-06 | `apply-pdf2zh-045c-sanitize.py` | `_QY_045C_SANITIZE` | IL | **D** | span/id 消毒 |
| D-07 | `apply-pdf2zh-ocr-base.py` | `_qy_ocr_*` | pdf_creater + gui | **D**/部分 **C** | 扫描底处理 |
| D-08 | `apply-pdf2zh-throughput.py` | unload/skip/batch markers | gui + IL | **B**+**D** | 吞吐；CLI 路径部分仍相关 |

CLI 是否命中上述补丁：**必须以** `scripts/plan071_patch_fingerprint.py` 探测结果为准，并写入任务快照。

## 3. 纯 UI / UX 补丁（B，不迁质量流水线）

| ID | 脚本 | 分类 |
| --- | --- | --- |
| U-01 | `apply-pdf2zh-brand.py` | B |
| U-02 | `apply-pdf2zh-downloads.py` | B |
| U-03 | `apply-pdf2zh-dual-preview.py` | B（Vue 071f 重做） |
| U-04 | `apply-pdf2zh-layout-polish.py` | B |
| U-05 | `apply-pdf2zh-adv-options.py` | B |
| U-06 | `apply-pdf2zh-left-dock.py` | B |
| U-07 | `apply-pdf2zh-prescan.py` | B + 少量 A（prescan 调 structure）→ structure 阶段复用逻辑 |
| U-08 | `apply-pdf2zh-040a/b/d-*.py`、`sse-recover`、`viewer`、`preview-*`、`settings-inline`、`no-store`、`css-has-fix`、`stale-guard`、`glossary-encoding` | B |
| U-09 | `apply-pdf2zh-050-workbench.py`、`060-browser-chrome.py` | B |
| U-10 | `apply-pdf2zh-038g-session-cancel.py` | B/会话 |

## 4. 新 runner 对照缺口

| 能力 | `workbench/runner.py` | 结论 |
| --- | --- | --- |
| imgtr / tbltr / graphic_reinsert / letter / doc_profile | 未调用 | **缺口** → 071c |
| HPD | 仅空产物重试 `_retry_scanned_pdf_with_hpd` | **弱于** GUI 译前 HPD → 071b/c |
| 成功终态 | 672–683 直接 succeeded/export/100 | **禁止** → 071b+071e |
| Office/图片 | 非 PDF 拒收；API 走 legacy | 能力在 sidecar，状态机未统一 → 071b |
| 金标后处理样板 | `gold/plan051_run.py` `_run_postprocess` | **可复用挂接方式** |

## 5. scripts 薄封装约定（071c）

迁移后 `scripts/*.py` 保留 re-export，保证 `pdf2zh.service` ExecStartPre 旧链路不破，直到 Gradio 退役计划单独立项。

## 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-10-01 | 071a 初版盘点，基于 patch-order 36 项 + 代码探查 |
