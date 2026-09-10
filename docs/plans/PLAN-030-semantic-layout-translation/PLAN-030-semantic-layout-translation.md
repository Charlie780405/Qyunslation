# PLAN-030 多格式、多题材文档结构语义与原位翻译闭环纲领

> 状态：**已批准**
> 日期：2026-09-07
> 批准记录：用户于 2026-09-07 明确批准 PLAN-030
> 关联：PLAN-027（文档内嵌图）、PLAN-028（预扫描）、PLAN-029（表格结构化）
> 阶段门：030a–030h、030j 已完成。Checkpoint C 三条已闭合；D1–D5 已清。
> 阶段门：030a–030j、**030i 已完成**。Checkpoint D 发布门已交付。
> 下一步：030-table Camelot 选型（Task 0）或 PLAN-034（暂停中）。

## 一、执行基线提示词

> 在 qyunslation 工作区，严格遵循项目的 plan → approve → detailed subplan → implement → verify → deploy 流程。以“多格式、多题材文档的结构化原位翻译”为目标，深度审查现有代码、测试、计划和运行证据。输入至少覆盖 PDF、DOCX、常见图片及 PPT/PPTX，并把文献、综述、演示文稿、Poster 等内容画像与文件格式解耦。重点核查：Figure 语义计数与底层位图/矢量对象计数是否混淆；Table 是否被识别、分类、翻译与原位重建；单栏、双栏、多栏、幻灯片和海报画布是否保持阅读顺序、层级和几何位置；图内文字是否完成 OCR、翻译、回填并替换原图；原生 Office 与图片化回退是否具有明确能力边界和产物血缘。先形成带证据、差距、目标架构、格式×题材验收矩阵、阶段划分、验收门和风险的开发计划纲领；未经用户批准，不生成详细开发子计划，不改业务代码、不部署。

## 二、审查结论

当前系统已经具备 PDF 位图/矢量区域和独立图片的 OCR 嵌字能力，也具备 DOCX/PPTX 原生文字翻译及 BabelDOC 正文版面分析能力；但这些能力分散在不同入口和工作流中，距离预期目标仍有结构性差距：

1. **预扫描统计的是物理资源或候选区域，不是论文语义对象。** `candidate_count` 表示唯一位图 xref，`vector_count` 表示矢量聚类区域，最终直接相加为“插图数”。同一 Figure 的位图、矢量、题注可能重复计数，也可能因共享 xref 被少计。
2. **表格识别链路不统一。** 上传预扫描使用 PyMuPDF `find_tables()`；Markdown 导出使用跨仓 Hermes `lit_tables`；正文 PDF 使用 BabelDOC DocLayout。三个结果没有统一对象 ID、置信度或消费关系。
3. **PLAN-028 的验收口径固化了原始检测框数。** 固定样本实跑为 12 个矢量区域、26 个 `find_tables` 区域，而 BabelDOC DocLayout 对同一文件识别为 10 个 figure 区域、3 个 table；Hermes 语义抽取也是 3 个 Table。区域数不能作为 Figure/Table 数。
4. **目标论文基线未进入测试。** `ljae439.pdf` 的正确用户语义是 Figure 1–5、Table 1–3；现状截图显示“5 位图 + 2 矢量 = 7 插图”，且未展示 Table。
5. **“预扫描—执行一致”目前只是复用部分函数，不是复用同一份结构结果。** PLAN-028 明确不把 Tier-3 结果缓存给翻译阶段；执行阶段会重新检测，幻灯页还使用不同参数。
6. **表格执行能力存在依赖版本漂移。** pdf2zh-next 2.9.0 仍传入 `table_model`，但当前 BabelDOC 0.6.2 已明确忽略该参数并移除 RapidOCR TableParser；现有配置、文案和验收未覆盖该变化。
7. **多栏原位翻译缺少项目级证明。** 底层 DocLayout/ParagraphFinder 有布局能力，但本仓没有单栏、双栏、多栏的金样、阅读顺序断言、跨栏串接检测、几何漂移指标或端到端回归。
8. **错误与截断可能伪装成“未检测到”。** `find_tables()` 异常被吞掉；Tier-3 的 `error` 未进入 UI；Tier-1 最多 20 个候选、Tier-2 只探测前 10 个，却没有把不完整状态明确呈现给用户。
9. **部署结构不可复现。** 关键能力依靠脚本修改已安装的 `site-packages/pdf2zh_next/gui.py`，并通过绝对路径依赖 `/home/dev/Hermes/scripts`；升级或换机可能静默丢失表格/预扫描能力。
10. **文件格式能力没有统一契约。** 当前 GUI 旁路只接入 PDF、DOC/DOCX、PNG/JPEG，服务端却另有 PPTX 和更多转换入口；WebP、BMP、TIFF、PPT/PPTX 等在上传、预扫描、自动路由和执行阶段的支持集合彼此不一致。
11. **PPT/PPTX 图片化链路尚未闭环。** PPTX 原生工作流能遍历文本框、表格、备注和母版文本，但不处理 picture shape 内文字；`.ppt` 会被自动路由为 PPTX，实际工作流却只接受 `.pptx`。统一 GUI 旁路目前也未接入 PPT/PPTX。
12. **内容题材与文件格式被混为一谈。** 现有 PDF 画像仅有 letter/literature/regulatory/generic；没有 review、presentation、poster 的结构规则，也无法表达“Poster 是图片”“综述是 DOCX”或“PPT 已转成逐页图片”等组合。

因此，PLAN-030 不是继续调计数阈值或补后缀白名单，而是把各格式输入归一到“可追踪画布 + 语义结构清单”，再由格式能力与内容画像共同路由原位翻译。

## 三、目标与成功定义

### 3.1 用户目标

- 上传后明确展示语义级摘要，例如：`检测到 5 个 Figure、3 个 Table；其中 4 个 Figure 含待译文字。`
- 单栏、双栏、多栏文档都保持原页面尺寸、栏位、阅读顺序、题注关系和对象位置。
- Figure 内文字经 OCR/翻译后在原位替换；无可译文字的 Figure 原样保留。
- Table 被独立识别；原生文字表优先按单元格/文字层翻译，扫描表才进入 OCR 重建或显式降级。
- 预扫描、执行、产物审计使用同一批语义对象，所有跳过和失败均可解释。
- 至少支持 PDF、DOCX、常见图片、PPT/PPTX；同一入口准确识别真实格式、能力和降级方式。
- 文件格式与内容画像分离：同一 PDF 可是论文、综述、PPT 导出版或 Poster，同一 Poster 也可来自图片、PDF 或 PPTX。
- PPT/PPTX 同时提供原生可编辑模式和“逐页图片化翻译”模式；后者明确输出为图片化幻灯片，不伪装成可编辑文字。
- Poster 按单画布/大画布处理，保持分区、对齐、视觉层级和长宽比，不按普通正文强行串接。

### 3.2 首批硬验收

| 维度 | 硬验收 |
| --- | --- |
| `ljae439.pdf` | 语义清单严格为 Figure 1–5、Table 1–3；不得显示 7 个插图；补充材料编号不得混入正文计数 |
| 格式基线 | PDF、DOCX、PNG、JPEG、WebP、BMP、TIFF、PPTX 可从统一入口完成能力探测；`.doc`/`.ppt` 必须显式转换或明确拒绝，不得路由后才失败 |
| 计数口径 | UI 主计数按唯一语义编号/无编号对象；位图、矢量、XObject、drawing 数只作为诊断明细 |
| 预扫一致性 | 执行阶段消费预扫描 manifest；对象 ID、页码、bbox、类型和最终状态可逐项对账 |
| 原位版式 | 页数、MediaBox/CropBox/旋转不变；正文不跨栏串接；Figure/Table footprint 不越出原区域 |
| DOCX | 输出仍为可打开、可编辑 DOCX；节、栏、页眉页脚、表格、文本框和图片 occurrence 不丢失，嵌图按实例翻译 |
| PPT/PPTX 原生模式 | 幻灯片数量、尺寸、顺序、母版关系和对象层级不变；原生文字/表格与嵌入图片均有执行状态 |
| PPT/PPTX 图片化模式 | 每页按固定 DPI/色彩/字体环境渲染；逐页原位翻译后可导出图片集、图片型 PDF 和图片背板 PPTX，顺序与画布尺寸不变 |
| 独立图片/Poster | 图像方向、像素尺寸、长宽比、透明通道和非文字区域保持；超大画布分块处理后无接缝、无错序 |
| 图片替换 | 每个 `translate_required` Figure 必须为 translated、explicitly_skipped 或 failed-soft 三态之一；不得静默遗漏 |
| 表格翻译 | 表题、表头、文本单元格可翻译；数字、单位、统计符号不变；表格不能被误算为 Figure |
| 可搜索性 | 非扫描正文和原生表格译文保持可选、可搜；不得把整页无条件栅格化 |
| 降级行为 | 结构置信度不足或执行失败时保留原对象，并在 UI/manifest 中显示原因 |

## 四、目标架构

### 4.1 单一结构清单 `DocumentStructureManifest`

建立仓内版本化契约，作为预扫描、翻译执行、UI 和验收的唯一事实源：

```text
DocumentStructureManifest
├── document
│   ├── hash / schema_version / source_format / detected_mime
│   ├── container_mode(native|rendered|hybrid) / content_profile / profile_confidence
│   └── input_asset / derived_assets[] / conversion_lineage[] / scan_status
├── canvases[]
│   ├── kind(page|section|slide|poster) / source_index / dimensions / rotation
│   └── layout_mode(single|double|multi|mixed|freeform) / columns / regions / reading_order
└── objects[]
    ├── semantic_id: figure:1 | table:3 | slide:2:title | poster:section:methods
    ├── type: figure | table | body | caption | text_box | shape | image | poster_section
    ├── representation: bitmap | vector | hybrid | native_text | scanned
    ├── canvas_id / bbox / column_id / z_order / caption_bbox / caption_text
    ├── source_refs: xref[] / drawing[] / text_block[] / ooxml_part[] / shape_id[]
    ├── confidence / detector_evidence[] / translatable_blocks
    └── planned_action / execution_status / output_evidence
```

主计数取 `semantic_id` 去重；物理资源数永远不再直接显示为 Figure 数。

### 4.2 输入归一化与产物血缘

| 输入 | 原生路径 | 归一化/回退路径 | 主要输出 |
| --- | --- | --- | --- |
| PDF | 文字层、页面对象、矢量和位图联合解析 | 扫描页按页面画布 OCR；局部对象栅格化 | 原位 PDF + manifest |
| DOCX | OOXML 段落、节/栏、表格、文本框、DrawingML | 必要时生成只读页面渲染用于视觉校验，不替代原生编辑输出 | 可编辑 DOCX + HTML/页面预览 + manifest |
| 图片 | EXIF 归一、颜色/透明度保留、全画布 OCR | 超大图分块；SVG/HEIF/AVIF/GIF 等经能力探针后解码或明确拒绝 | 同格式优先；必要时显式 PNG/TIFF + manifest |
| PPTX | 原生 shape/table/text/image/notes/master 解析 | 每页渲染成图片进行视觉翻译；复杂对象可按用户选择走图片化模式 | 可编辑 PPTX 或图片化 PPTX/PDF/图片集 + manifest |
| PPT | 先经受控 Office 转换并记录转换器版本与 hash | 转 PPTX 失败时仅允许显式图片化或 fail-fast | 规范化 PPTX 或图片化产物 + manifest |

任何转换都记录 `source → normalized → translated → packaged` 血缘；UI 必须说明产物是否保留可编辑性。

### 4.3 检测融合顺序

1. **快速文本层**：解析 Figure/Table 题注、编号、页码和候选区域，先得到可解释的语义锚点。
2. **DocLayout 层**：对候选页识别 figure/table/caption/正文布局，作为单/双/多栏和无边框表的结构证据。
3. **物理对象层**：枚举 bitmap xref、vector drawings、文字块和 bbox，关联到语义锚点，而不是自行形成用户计数。
4. **OCR 层**：只对已归类的 Figure 或扫描 Table 执行，用于判断是否需要翻译和生成块级计划。
5. **冲突消解**：Table 优先于通用 vector region；同一题注邻域内的多面板/多资源合并为一个 Figure；无编号对象单独标注且不伪造编号。

### 4.4 对象执行分流

| 对象 | 默认策略 | 禁止行为 |
| --- | --- | --- |
| 正文 | BabelDOC 按 layout/column/reading order 翻译并原位排版 | 只按 PDF 内容流顺序串接多栏 |
| 原生 Table | 保持单元格/文字层和线框，逐单元格或表格文字块翻译 | 当作 Figure 整块 OCR；只在 Markdown 旁路可用 |
| 扫描 Table | OCR 结构化、数字保护、原区域重建；低置信度 fail-soft | 未检测表结构却宣称“按文字层翻译” |
| bitmap Figure | occurrence-first，图内 OCR/翻译/回嵌 | 用唯一 xref 数冒充 Figure 数；污染共享资源 |
| vector/hybrid Figure | 按语义 bbox 栅格化翻译并覆盖，保留区域外文字/矢量 | 纵向聚类后直接计数；整页栅格化回退 |

### 4.5 格式输出策略

- **PDF**：保留页面几何与可搜索文字；只有扫描页或局部复杂对象允许栅格处理。
- **DOCX**：原生 XML 内替换正文、表格、文本框和图片实例；页面渲染只做视觉验收，不作为默认交付。
- **图片/Poster**：以全画布空间关系为主，OCR 块按分区排序，译文直接回填图片；分块结果必须无接缝合成。
- **PPTX 原生模式**：翻译原生文本和表格，图片 shape 走嵌图翻译；对溢出采用字号、行距、文本框约束的可解释阶梯。
- **PPT/PPTX 图片化模式**：逐页渲染后调用图片/Poster 画布链路；输出以图片为真值，可额外封装回 PPTX/PDF，但不承诺对象级可编辑。

### 4.6 内容画像独立于格式

首批画像为 `research_article`、`review_article`、`presentation`、`poster`、`regulatory`、`letter`、`generic`。画像只决定结构先验、阅读顺序、术语和排版约束，不决定文件解析器；自动识别必须允许用户覆盖，并在 manifest 记录最终选择与依据。

## 五、阶段纲领与批准门

> 下列仅定义子计划边界；批准后再分别形成详细任务、文件清单、测试用例和回滚步骤。

| 拟编号 | 阶段 | 目标 | 依赖 |
| --- | --- | --- | --- |
| 030a | 跨格式契约与红色基线（已完成） | 固定 manifest schema、格式能力表、内容画像、Figure/Table 口径和格式×题材金样；记录格式/画像解耦及原生/图片化双模式 ADR；先让现状测试失败 | 无 |
| 030b | 输入适配与归一化画布 | 统一 MIME/扩展名探测、PDF/DOCX/图片/PPT(X) 接入、Office 转换、图片解码、产物血缘和能力探针 | 030a |
| 030c | [统一语义扫描与题注驱动归并](./PLAN-030c-unified-semantic-scan.md)（已完成） | 题注锚点 + 物理对象关联 → manifest；预扫描/UI 语义计数；纯表页 fail-closed 执行防护 | 030a–030b |
| 030d | [PDF 纵向闭环](./PLAN-030d-manifest-ssot-execution-parity.md)（已完成） | manifest SSOT 贯通、无编号对象、执行状态回写、正文 BODY 与阅读顺序、单/双/多栏检测、表格区域保护、原生/扫描/混合逐页对齐 | 030c |
| 030e | [DOCX 纵向闭环与前序缺口收拢](./PLAN-030e-docx-vertical-closure.md)（已完成） | DOCX 结构扫描、manifest 对账、单元格级表格、结构校验门；收拢 LibreOffice/样本/契约债 | 030c–030d |
| 030f | 图片与 Poster 纵向闭环 | 常见图片格式、超大画布分区、方向/透明度/色彩保护、无接缝回填与 Poster 画像 | 030c |
| 030g | [PPT/PPTX 双模式闭环](./PLAN-030g-pptx-dual-mode-closure.md)（已完成） | 原生嵌图关 `QY030-PPT-001`、`.ppt` 规范化、逐页图片化打包；瘦门禁不嵌套全门 | 030b–030f |
| 030h | [跨格式版式保真与入口一致性](./PLAN-030h-cross-format-fidelity.md)（已完成） | 验收脱离运行时样本目录、GUI 入口格式统一到能力矩阵、跨格式语义对账、单/双/多/混合栏与 Poster 分区版式金样；栏式判定的五处缺口已登记为 D1–D5 待另立子计划 | 030d–030g |
| 030j | [栏式判定债 D1–D5](./PLAN-030j-layout-debt.md)（**已完成**） | 030ja–030jd | 030h |
| 030i | [UI、可观测、兼容与交付](./PLAN-030i-delivery-closure.md)（**已完成**） | 030ia–030id：画像/模式 UI、manifest 下载、依赖探针、补丁供应链与 Checkpoint D | 030j |

### Checkpoint A：030a 后

- 人工确认“Figure/Table/物理资源”的口径与样本真值。
- 人工确认格式能力表、PPT/PPTX 原生/图片化双模式及 `.doc`/`.ppt` 转换边界。
- `ljae439` 通过知识库作为开发/验收样本来源；仓内保存语义 truth 与稳定 locator，实体导入后记录完整 hash。生产上传链路不得依赖知识库。
- 每个必选格式和首批画像至少有一个可合法复现的金样或合成夹具。
- 未通过不得进入检测器实现。

### Checkpoint B：030b–030c 后

- 同一输入重复扫描得到稳定 manifest。
- UI 预扫与执行读取同一 `schema_version + document_hash`。
- `ljae439` 达到 5 Figure / 3 Table，且每个对象有题注与 bbox 证据。
- 同内容经 PDF、DOCX、图片和 PPTX 承载时，语义对象可对账；转换产物具有 hash、转换器版本和可编辑性标记。（030c 仅交付 PDF；跨格式对账推迟至 030g 之后，见 PLAN-030c §五。）

### Checkpoint C：030d–030g 后

- PDF、DOCX、图片/Poster、PPT/PPTX 各自完成至少一条端到端纵向闭环。
- Figure/Table 不互相误分类；原位对象无越界；阅读顺序无跨栏串接。
- 图片 OCR 残留、表格数字保护、正文可搜索性、Office 可打开性和图片化幻灯片完整性均有自动断言。

判定（030h 后）：前两项闭合，第三项闭合。第二项的「阅读顺序无跨栏串接」仅在单/双栏成立——
030h 的版式金样查明三栏及以上被判成 DOUBLE 后中栏归左，海报九分区被串成两栏，均属跨栏串接。
D1、D2、D4 等五处债已于 [PLAN-030j](./PLAN-030j-layout-debt.md) 清理；030i 负责 Checkpoint D 发布门。

### Checkpoint D：030h–030i 发布前

- 本仓单命令验证，不依赖“样本缺失则 skip”的假绿。
- 锁定并验证 pdf2zh-next/BabelDOC/PyMuPDF 版本语义。
- 锁定并验证 Office 转换器、图片编解码器、字体与渲染环境；无能力时在上传前 fail-fast。
- 生产补丁可幂等、可回滚；升级后有兼容性失败门禁。
- 用户批准视觉金样后才允许部署。

## 六、测试与度量纲领

### 6.1 样本矩阵

测试矩阵是“文件格式 × 内容画像 × 布局/对象表示”的笛卡尔积，首批至少覆盖：

| 维度 | 必测组合 |
| --- | --- |
| PDF | 原生、扫描、混合；research article、review、PPT 导出、Poster；单/双/多/混合栏 |
| DOCX | 单栏与分节多栏；research/review、generic；正文、原生表、文本框、页眉页脚、共享/裁剪图片 |
| 图片 | PNG、JPEG、WebP、BMP、单/多页 TIFF；普通信息图、扫描页、超长图、透明图、Poster；EXIF 旋转 |
| PPT/PPTX | 原生 PPTX、legacy PPT 转换、逐页图片化输入；presentation、学术汇报、Poster；文本框、表格、组合形状、母版、备注、嵌图 |
| Figure/Table | bitmap、纯 vector、hybrid、扫描表、无边框表、多面板 Figure、续表、跨栏题注 |
| 复用 | 共享 xref/ImagePart、同图多 occurrence、页眉 logo 与正文图共用资源、母版图跨页复用 |
| 失败 | 加密、损坏、伪后缀、解码器缺失、Office 转换失败、字体缺失、超时、低置信度、超大画布/页数 |

### 6.2 自动指标

- **语义准确率**：Figure/Table 编号集合与金标完全一致；另报 precision/recall，不只报总数。
- **格式契约**：扩展名、MIME、魔数、自动路由和实际执行能力一致；支持矩阵逐项 contract test。
- **关联准确率**：题注—对象、对象—物理资源、对象—执行结果一一可追踪。
- **版式完整性**：页框、旋转、页数不变；栏边界越界为 0；非目标区域像素/矢量无异常损伤。
- **文本完整性**：正文段落与表格文本无缺失、无重复、无跨栏错序；数字集合保持。
- **图片质量**：沿用 SK-Q002 C1–C10，并新增文档级 bbox、DPI、原文残留和 occurrence 对账。
- **Office 完整性**：DOCX/PPTX 可重新打开并二次保存；节/幻灯片/shape/relationship 数量异常变化为 0；图片化模式逐页像素基线可对账。
- **画像准确性**：自动画像单独报告准确率；错误时允许覆盖且不影响格式解析，禁止把画像误判变成文件不支持。
- **性能**：快速层与语义核验层分别计时；UI 明确区分“初步”与“已核验”，超时不得伪装为 0。

## 七、关键风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 题注缺失或编号异常 | 无法仅靠编号归并 | DocLayout + 邻域图 + 连续性评分；低置信度对象标 unnumbered/needs_review |
| 多面板 Figure 被拆分 | 计数偏大、重复翻译 | 以题注为锚合并物理组件，面板字母作为子对象而非新 Figure |
| Table 被矢量聚类吞掉 | 表格不显示且被当图片 | 检测顺序 Table-first；冲突时语义模型/题注优先，vector detector 只消费剩余区域 |
| DocLayout 计算较慢 | 上传等待过长 | 快速题注层先反馈；后台只扫候选页；缓存 manifest；展示核验状态 |
| 中译文膨胀导致跨栏 | 串栏、遮挡 | column hard boundary + 字号/行距阶梯 + 显式 overflow 状态，禁止静默越界 |
| 依赖升级改变行为 | 配置名存在但实际 no-op | 启动时能力探针 + 版本契约测试；禁止只 grep 配置名判成功 |
| 绝对路径/跨仓依赖 | 换机或部署后静默降级 | 将结构契约与核心检测迁回本仓；外部适配器显式 capability/error |
| Office 转换或字体环境漂移 | PPT/DOC 渲染在不同机器不一致 | 固定转换器、字体包、locale 和 DPI；记录版本；视觉基线按环境签名分组 |
| 图片化 PPT 丢失可编辑性 | 用户误以为还能编辑文字对象 | 原生/图片化模式分开选择；产物命名、UI 和 manifest 明示 `editable=false` |
| 超大 Poster/长图耗尽内存 | 任务崩溃或输出接缝 | 带重叠的分块 OCR/修复、坐标回映、内存预算和接缝检测 |
| 声称“支持各种图片”但运行时缺解码器 | 上传后才失败或错误转码 | 魔数+能力探针；核心格式设硬门，扩展格式动态列出并在上传前明确结果 |

## 八、范围边界

### 本期包含

- PDF：原生、混合和扫描文档的语义识别、原位翻译与审计。
- DOCX：正文、节/栏、原生表、文本框、页眉页脚和嵌图的可编辑原位翻译。
- 图片：PNG/JPEG/WebP/BMP/TIFF 硬支持；SVG/GIF/HEIF/HEIC/AVIF 等通过能力探针纳入扩展支持或在上传前明确拒绝。
- PPT/PPTX：原生可编辑 PPTX 与逐页图片化翻译双模式；legacy `.ppt` 经显式转换后处理。
- 内容画像：文献、综述、PPT/演示、Poster、regulatory、letter、generic；格式与画像可任意合法组合。
- 单栏、双栏、多栏/混合栏、幻灯片自由布局和 Poster 分区验收。
- Figure 1–N 与 Table 1–N 的语义计数、题注关联、翻译策略与 UI 反馈。

### 本期不包含

- 图片化模式下 SmartArt、Chart、OLE 等复杂 Office 对象的可编辑对象级重建；其视觉内容仍必须被图片化翻译或明确跳过。
- 动画、切换、音视频内容的语言重制；原生 PPTX 模式只要求不主动破坏这些关系。
- 将 legacy `.doc`/`.ppt` 原样作为交付格式；统一规范化为 DOCX/PPTX 或图片化产物。
- 对无文字照片做超分、重绘或风格转换。
- 以 Markdown 表格替代 PDF 原位表格。
- 在计划获批前调整线上阈值、补丁或服务。

## 九、批准记录与下一门

用户已于 2026-09-07 批准以下方向：

1. 以 **语义 Figure/Table 数** 替代位图/矢量区域相加的用户计数。
2. 建立 `DocumentStructureManifest` 作为预扫描与执行 SSOT。
3. 把 `ljae439` 的 **5 Figure / 3 Table** 设为第一硬基线。
4. 将 PDF、DOCX、常见图片、PPT/PPTX 设为首批硬格式，并用能力探针管理扩展图片格式。
5. 将文件格式和内容画像解耦；文献、综述、PPT/演示、Poster 等分别建立结构先验和验收样本。
6. PPT/PPTX 提供原生可编辑与逐页图片化双模式；`.ppt`/`.doc` 先规范化，不承诺旧二进制格式原样交付。
7. 将单栏、双栏、多栏、自由布局和 Poster 分区作为独立质量门，而不是依赖底层库“应当支持”。
8. 依次编写 030a–030i 详细子计划；每份子计划再次单独审批后实施。

030a 完成记录：[PLAN-030a](./PLAN-030a-cross-format-contract-baselines.md) / [WT-030a](../../walkthroughs/WT-030a-contract-baselines.md)。
030b 完成记录：[PLAN-030b](./PLAN-030b-input-adapters-normalized-canvases.md) / [WT-030b](../../walkthroughs/WT-030b-input-adapters-normalized-canvases.md)。
030c 完成记录：[PLAN-030c](./PLAN-030c-unified-semantic-scan.md) / [WT-030c](../../walkthroughs/WT-030c-unified-semantic-scan.md)。

030d 完成记录：[PLAN-030d](./PLAN-030d-manifest-ssot-execution-parity.md) / [WT-030d](../../walkthroughs/WT-030d-pdf-vertical-closure.md)。用户于 2026-09-08 批准全量范围并在实施中据实测证据决策两处修订：正文不接 BabelDOC DocLayout（本仓 venv 缺 `babeldoc`、CPU 1.08s/页超预扫描预算、且它不产出栏位与阅读顺序），改自研几何；PDF 表格由「原位重建」降级为「区域保护」（`find_tables()` 在无竖线三线表上召回 2/6 且假阳性严重，`strategy="text"` 会拦腰切断数值，无法满足数字逐 token 保护红线）。单元格级重建待技术选型后另立项。

Checkpoint C 尚未达成：它要求 030d–030g 四条纵向闭环齐备，030d 只交付了 PDF 一条。
