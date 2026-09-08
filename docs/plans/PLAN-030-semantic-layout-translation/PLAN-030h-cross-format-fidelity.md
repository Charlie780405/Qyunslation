# PLAN-030h 子计划：跨格式版式保真与入口一致性

> 状态：**已完成**
> 日期：2026-09-08
> 批准记录：用户于 2026-09-08 批准「按最佳建议推进」
> 父计划：[PLAN-030](./PLAN-030-semantic-layout-translation.md)（已批准）
> 前置：[PLAN-030d](./PLAN-030d-manifest-ssot-execution-parity.md)、[PLAN-030e](./PLAN-030e-docx-vertical-closure.md)、[PLAN-030f](./PLAN-030f-image-poster-closure.md)、[PLAN-030g](./PLAN-030g-pptx-dual-mode-closure.md)
> 验收门：`bash scripts/verify-plan-030h.sh`（**禁止**嵌套 028/029/030c–030g 全门）

## 目标

关闭父纲领 Checkpoint C 的最后一条，并为 Checkpoint D 的「本仓单命令验证，不依赖『样本缺失则 skip』的假绿」铺路。

四件事：验收基线搬进仓内、GUI 入口格式统一到能力矩阵、跨格式语义对账、版式金样补齐。

## 背景：为什么现在做

三条线索指向同一个问题——**契约声明的能力，没有任何断言在管**：

1. `capabilities.py` 把 WebP/BMP/TIFF 登记为 `CORE`，但生产 GUI 的文件选择器选不到它们。
2. `LayoutMode` 声明 `MULTI`，`profiles.py` 把它写进 `RESEARCH_ARTICLE` 的 `expected_layout_modes`，但 `detect_layout_mode` 从不产出 `MULTI`。
3. 父纲领 Checkpoint B 要求「同内容经四种格式承载时语义对象可对账」，此前推迟到 030g 之后，一直没人验。

第三条的验收还锚定在 `/home/dev/pdf2zh/pdf2zh_files/<uuid>/`——那是 pdf2zh 的**运行时会话目录**，会随会话回收，换机必然缺失，缺失时门只报 skip，于是「全绿」并不代表验过。

## 交付

### H1 验收基线脱离运行时样本目录

新增三份合成等价夹具，主门断言改走仓内合成件；仓外真实金样降级为「加强回归」，缺失只报 INFO 不再 BLOCKED。

| 夹具 | 等价于 | 关键性质 |
| --- | --- | --- |
| `scanned-equivalent.pdf` | 20 页扫描件 | `document_representation=SCANNED`、`needs_ocr=True`、`selected_mode=HYBRID` |
| `scanned-equivalent.hpd-ocr.pdf` | 同一文档 OCR 后 | `HYBRID` 表示，OCR 清单清零 |
| `slide-equivalent.pdf` | 16:9 无题注幻灯 | `FREEFORM` 版式、12 个可译区 |

`conftest.py` 提供 `scanned_pdf` / `ocr_pdf` / `slide_pdf` 三个间接夹具，用 `both_scanned` / `both_ocr` / `both_slides` 装饰器做双轨参数化：合成件恒跑，外部件在场才跑。

顺带修掉 `verify-plan-028.sh` 的一个真 bug：设了 `QYUNSLATION_SAMPLE_ROOT` 但里面找不到样本时，它返回一个不存在的路径直接 BLOCKED——而那份 `nature_comm_53384.pdf` 本来就在仓内 `tests/fixtures/structure/reference/`。

### H2 GUI 入口格式统一到能力矩阵

`capabilities.py` 新增 `gui_extension_manifest()` 及 `gui_upload_extensions` / `gui_sidecar_extensions` / `gui_image_extensions` / `gui_image_mime_types`，作为入口扩展名的单一事实源。`CONDITIONAL` 级（SVG/GIF/HEIF/HEIC/AVIF）依赖运行时探针，不进 GUI 入口。

补丁注入的代码运行在 pdf2zh 进程里，那里没有 `qyunslation` 包，所以扩展名必须在**打补丁时**渲染成字面量。新增 `scripts/_gui_extensions.py` 承担渲染；清单载入失败时直接 `SystemExit`，宁可服务起不来也不用过期字面量打补丁。

改造前后的七处漂移：

| 位置 | 改造前 | 缺失格式 |
| --- | --- | --- |
| `office-route` `file_types` | pdf/doc/docx/ppt/pptx/png/jpg/jpeg | webp/bmp/tif/tiff |
| `office-route` `_QY_OFFICE_SIDECAR_EXT` | + webp | bmp/tif/tiff |
| `office-route` 图片分派 | png/jpg/jpeg/webp | bmp/tif/tiff |
| `dual-preview` `file_types` ×2 | pdf/doc/docx/png/jpg/jpeg | ppt/pptx/webp/bmp/tif/tiff |
| `prescan` 图片判定 | png/jpg/jpeg/webp/bmp | tif/tiff |
| `preview-url` 图片判定 | png/jpg/jpeg/webp | bmp/tif/tiff |
| `office-preview` 预览扩展名 + MIME 表 | png/jpg/jpeg/webp | bmp/tif/tiff |
| `custom_api.py` image-probe ×2 | png/jpg/jpeg/webp/bmp | tif/tiff |

`file_types` 顺带补齐大写变体：历史补丁只手工加了 `.PDF`，`.DOCX` 等大写后缀一律选不中。

`dual-preview` 不再硬编码 `file_types` 锚点——上游 `office-route` 会把它改写成清单形态，写死锚点必然在清单变更时静默失配（这条链路早已失配，只是没人发现）。

补丁的幂等判定也补了自愈：`office-route` 把清单字面量纳入 `needs_refresh` 条件，`office-preview` 新增 `refresh_extension_sets()` 就地升级已注入的旧集合。没有这一步，marker 已存在时集合永远不会更新。

### H3 跨格式语义对账

新增四份承载**同一内容**的夹具（`parity.pdf` / `.docx` / `.pptx` / `.png`：一段正文、一张带 Figure 1 题注的图、一张带 Table 1 题注的表），断言语义身份哪些守恒、哪些不守恒、不守恒该由什么解释。

| 承载物 | 编号语义身份 | 差异归因 |
| --- | --- | --- |
| PDF | `figure:1` `table:1` `caption:figure:1` `caption:table:1` | 基准 |
| DOCX | 与 PDF **逐项相等** | 正文分段数不同（页级切分 vs 段落级切分） |
| PPTX | 无 | `semantic_id` 带幻灯片坐标（`table:slide:1:N`），题注以 `TEXT_BOX` 承载——形状是幻灯片的一等公民，没有文档流可依附 |
| PNG | 无 | 压平成单个 `IMAGE`，由 `output_editability=RASTERIZED` 解释 |

### H4 版式金样

新增 `three-column.pdf` / `four-column.pdf` / `mixed-columns.pdf` / `poster-sections.pdf`。

夹具改用 `pymupdf.insert_textbox` 而非裸内容流：裸流里同一行的多段文字会被合并成一个横跨整页的块，栏式判定看到的 narrow 块数不足，测不出真实行为——最初的双栏合成件就是这样一直被判成 SINGLE 而无人察觉。

pymupdf 每次生成的 trailer `/ID` 都不同，加 `_canonicalize_pdf()` 固定，否则 catalog 的 sha256 不可复现。

## 发现的债（本子计划只登记，不修）

修这四条都要动判定逻辑核心，会牵动 `profiles.py` 的版式策略和 nature 双栏样本的既有断言，须另立子计划。现状已被断言锁住，修好时断言会转红提醒摘除。

| # | 债 | 后果 | 证据 |
| --- | --- | --- | --- |
| D1 | 三栏、四栏一律判 `DOUBLE`，`LayoutMode.MULTI` 是死枚举 | 契约声明支持 MULTI，实现无从表达栏数 | `test_multi_column_mode_is_never_produced` |
| D2 | 三栏页中间栏压在中线上，被归入左栏 | 阅读顺序在扫描阶段就错乱，后续排版补不回来 | `test_middle_column_is_swallowed_by_the_left_column` |
| D3 | 正文块少于 3 的双栏页短路成 `SINGLE` | 短文、附录、表格页丢栏 | `test_two_column_page_with_few_blocks_falls_back_to_single` |
| D4 | A0 海报宽高比 1.41 够不着 `SLIDE_ASPECT=1.55` | 九块独立分区被当成期刊双栏正文串接，`POSTER_SECTION` 在 PDF 通道完全没被识别 | `test_poster_is_not_recognised_as_freeform` |
| D5 | `content_profile` 由扫描器按格式硬编码 | `scan_pdf` 恒给 `RESEARCH_ARTICLE`、`scan_docx` 恒给 `REVIEW_ARTICLE`，同一内容换容器就换 profile | `test_content_profile_is_bound_to_the_container_not_the_content` |

## 验证（瘦）

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | `compileall` capabilities + custom_api + 五个补丁脚本 | 通过 |
| V2 | `pytest tests/structure --no-cov` | 全绿，0 xfail |
| V3 | 无外部样本重跑 `tests/structure` | 零失败，只有 skip |
| V4 | `pytest tests/structure/test_gui_extension_manifest.py` | 含「已安装 GUI 与清单一致」 |
| V5 | 五种图片格式过 sidecar `image-probe` | 全部受理，无 `unsupported_format` |
| V6 | `verify-plan-028.sh` 在 `SAMPLE_ROOT` 指向空目录时 | PASS，blocked=0 |

## Out of Scope

- 修 D1–D5（另立子计划）
- 视觉像素级回归（Checkpoint D）
- `CONDITIONAL` 格式（SVG/GIF/HEIF/AVIF）进 GUI 入口
- 030i 的 UI、可观测与交付
