# PLAN-030a 子计划：跨格式契约与红色基线

> 状态：**已完成**
> 日期：2026-09-07
> 批准记录：用户于 2026-09-07 明确批准 PLAN-030a
> 完成记录：[WT-030a](../../walkthroughs/WT-030a-contract-baselines.md)
> 父计划：[PLAN-030](./PLAN-030-semantic-layout-translation.md)（已批准）
> 阶段门：030a 仅交付契约、夹具、测试与文档，未接入生产入口、未部署；下一步须单独编写并审批 030b。

## 一、目标

建立 PLAN-030 后续所有格式适配器、扫描器、执行器、UI 和验收共同依赖的第一版稳定契约，并把已知错误固化为可执行红色基线。

030a 只回答四个问题：

1. 一个 PDF、DOCX、图片或 PPT/PPTX 输入，如何被一致地描述和追踪？
2. “格式支持”“运行环境可用”“内容画像”“输出是否可编辑”如何分别表达？
3. Figure、Table、正文、文本框、嵌图和 Poster 分区如何获得稳定身份及明确状态？
4. 后续实现必须通过哪些金标和失败基线，才能证明没有继续制造假计数、假支持或假成功？

### 完成定义

- `DocumentStructureManifest v1` 的 Python 类型、JSON Schema、错误语义和兼容策略通过契约测试。
- 格式能力注册表与内容画像注册表分别建模，覆盖 PLAN-030 首批范围且不存在硬编码耦合。
- `ljae439` 的 5 Figure / 3 Table 真值、跨格式合成夹具矩阵及当前缺陷形成可执行基线。
- 默认测试套件保持可用；未实现行为以具名 `strict xfail` 保存，`--runxfail` 可证明它们当前确实失败。
- 不接入生产入口，不改变现有预扫描、翻译、导出或部署行为。

## 二、当前证据与边界

### 2.1 现有事实

- `scripts/doc_image_prescan.py` 只有 `pdf | docx | image` 粗粒度类型，候选对象没有语义 ID、坐标空间或执行状态。
- `scripts/apply-pdf2zh-office-route.py`、`scripts/doc_image_prescan.py` 与 `qyunslation/server/core.py` 的扩展名集合不一致。
- `qyunslation/server/core.py` 把 `.ppt` 和 `.pptx` 都路由为 PPTX；`qyunslation/workflow/pptx_workflow.py` 实际只接受 `.pptx`。
- `qyunslation/translator/ai_translator/pptx_translator.py` 遍历文本框、原生表、备注和母版文本，但不消费 picture shape 的图内文字。
- 现有 `Tier1Result`、`Tier3Result`、`PdfImgManifest`、DOCX `OverlayManifest` 和 `.graphics.json` 均为局部清单，字段与状态不可互换。
- 仓库已有 pytest/uv 和 `scripts/verify-plan-*.sh` 约定，但没有 ADR 目录或稳定结构契约约定。

### 2.2 030a 不做

- 不实现 MIME/魔数探测、Office 转换、图片解码、OCR、DocLayout 或结构扫描。
- 不修改 GUI、API 路由、sidecar、pdf2zh/BabelDOC 补丁及现有翻译执行器。
- 不把现有局部 manifest 立即迁移到 v1；只给出后续适配映射和弃用方向。
- 不提交未经许可的完整论文 PDF、商业 Poster 或演示文稿。

## 三、需冻结的契约决策

### 3.1 三个正交维度

| 维度 | 回答的问题 | 例子 |
| --- | --- | --- |
| `source_format` | 输入容器实际是什么 | `PDF`、`DOCX`、`PPTX`、`TIFF` |
| `content_profile` | 内容应按什么结构先验处理 | `RESEARCH_ARTICLE`、`REVIEW_ARTICLE`、`PRESENTATION`、`POSTER` |
| `processing_mode` | 本次以何种保真方式执行 | `NATIVE`、`RENDERED`、`HYBRID` |

任何合法组合都不得通过文件后缀暗中推断另一个维度。例如 `POSTER + PDF + NATIVE`、`POSTER + PNG + RENDERED` 和 `REVIEW_ARTICLE + DOCX + NATIVE` 都是合法输入。

### 3.2 能力声明与运行事实分离

格式注册表不得用一个 `supported=true` 同时表达产品承诺和当前机器状态：

```text
FormatCapability
├── requirement_level: CORE | NORMALIZE | CONDITIONAL | UNSUPPORTED
├── allowed_modes[]: NATIVE | RENDERED | HYBRID
├── required_features[]: decoder / office_converter / font_pack / renderer
└── runtime_state: AVAILABLE | DEGRADED | UNAVAILABLE | UNKNOWN
```

- `CORE`：PDF、DOCX、PNG、JPEG、WebP、BMP、TIFF、PPTX，发布门要求全部可用。
- `NORMALIZE`：DOC、PPT，必须先转换为 DOCX/PPTX 或显式选择图片化产物。
- `CONDITIONAL`：SVG、GIF、HEIF/HEIC、AVIF，由能力探针决定，上传前返回结构化结论。
- `UNSUPPORTED`：未知或高风险格式，必须 fail-fast，不能回退成 TXT。

### 3.3 Manifest v1 顶层结构

```text
DocumentStructureManifest
├── schema_version: "1.0.0"
├── manifest_id / created_at / producer
├── document
│   ├── source_sha256 / fast_fingerprint? / source_name
│   ├── source_format / detected_mime / content_profile / profile_source
│   ├── requested_mode / selected_mode / output_editability
│   └── input_asset / derived_assets[] / conversion_lineage[]
├── canvases[]
├── objects[]
├── issues[]
└── summary
```

关键约束：

- `source_sha256` 必须是完整文件 SHA-256；现有“最多读取 32 MiB”的 hash 只能进入 `fast_fingerprint`，不能作为文档身份。
- `schema_version` 采用语义版本；同一 major 只允许增加可选字段/枚举能力，新 major 才能删除或改变字段语义。
- 读取器对同 major 的未知可选字段前向兼容；写入器只能输出当前已知字段，扩展信息进入显式 `extensions` 命名空间。
- 未支持的 major 返回稳定错误码 `MANIFEST_VERSION_UNSUPPORTED`，不得静默猜测。

### 3.4 身份、坐标与来源

- `canvas_id` 使用稳定业务标识：`page:1`、`section:2`、`slide:3`、`poster:1`。
- `object_id` 是文档内唯一、确定性机器 ID；不得仅由易漂移的检测序号生成。
- `semantic_id` 是可选的人类语义标识，如 `figure:5`、`table:3`；正文/补充材料需有 `semantic_scope`，避免编号碰撞。
- canonical bbox 统一使用左上角原点，并显式携带 `unit`、`canvas_width`、`canvas_height` 和 rotation；OOXML EMU、PDF point、图片 pixel 等原始坐标保存在 `source_geometry`。
- 每个对象必须能追溯到 `source_refs`，其类型可为 PDF xref/drawing/text block、DOCX part/relationship、PPTX slide/shape 或图片 OCR block。

### 3.5 对象和状态使用判别联合

首批对象类型：

```text
BODY | CAPTION | FIGURE | TABLE | TEXT_BOX | SHAPE | IMAGE | POSTER_SECTION
```

首批执行状态：

```text
PENDING | TRANSLATING | TRANSLATED | EXPLICITLY_SKIPPED | FAILED_SOFT | FAILED_HARD
```

- 各对象类型通过 `type` 判别，类型专属字段不得散落为大量无条件 nullable 字段。
- `FAILED_SOFT` 必须保留原对象并带 reason code；`FAILED_HARD` 阻止伪成功产物。
- `summary` 必须从 `objects[]` 派生并通过校验，不接受调用方独立写入互相矛盾的计数。
- 稳定问题结构为 `code / severity / stage / object_id? / retryable / message / details`；业务逻辑依赖 `code`，不依赖可翻译文案。

### 3.6 内容画像

首批画像固定为：

```text
RESEARCH_ARTICLE | REVIEW_ARTICLE | PRESENTATION | POSTER |
REGULATORY | LETTER | GENERIC
```

`profile_source` 为 `AUTO | USER_OVERRIDE`。自动画像必须记录置信度和证据；用户覆盖不改变 `source_format` 或格式能力判断。

## 四、兼容与迁移原则

030a 不替换现有局部清单，防止契约建设意外改变线上行为。后续 030b/030c 通过 adapter 逐步读取：

| 旧来源 | v1 去向 | 迁移要求 |
| --- | --- | --- |
| `Tier1Result` / `Tier3Result` | `document.scan_status`、对象 detector evidence | 原始候选数只作诊断，不进入 Figure 主计数 |
| `PdfImgManifest` | Figure 对象 execution/output evidence | occurrence、xref、bbox 不丢失 |
| DOCX `OverlayManifest` | IMAGE/Figure source refs 与执行状态 | 共享 ImagePart 与实例 occurrence 分开 |
| `.graphics.json` | Figure/扫描对象 derived assets | 保留 DPI、区域和回插产物 hash |

旧字段在本阶段不删除、不改名；生产消费者未迁移前，v1 只作为并行契约存在。

## 五、金标与红色基线策略

### 5.1 金标夹具

| 夹具 | 形式 | 030a 真值 |
| --- | --- | --- |
| `ljae439` | 知识库 PDF 槽位 + 仓内 truth JSON | `figure:1..5`、`table:1..3`，正文范围，不把物理区域数当主计数 |
| synthetic PDF | 测试时确定性生成 | 单/双栏、跨栏 Figure、原生/扫描 Table、共享图资源 |
| synthetic DOCX | 测试时确定性生成 | 分节多栏、表格、文本框、页眉页脚、同图多 occurrence |
| synthetic images | 小型仓内或测试时生成 | PNG/JPEG/WebP/BMP/TIFF、透明通道、EXIF 旋转、长图/Poster |
| synthetic PPTX | 测试时确定性生成 | 文本框、表格、组合形状、母版/备注、含文字嵌图 |

`ljae439` 完整 PDF 不直接提交仓库。根据用户 2026-09-07 的范围调整，030a 记录稳定的知识库 locator 与语义 truth 即可；文件实体导入时再写入完整 SHA-256，并在 030b 字节级扫描验收前 fail closed。实体尚未导入不阻塞 030a 契约阶段。

知识库仅是开发/验收夹具来源，不是生产运行时依赖。真实产品入口保持为用户上传任意受支持资料；格式识别、结构扫描、翻译和输出链路不得调用该知识库。

### 5.2 红色基线

采用 `pytest.mark.xfail(strict=True, reason="PLAN-030x: ...")` 保存尚未实现行为：

- 当前 `5 bitmap + 2 vector` 被展示为 7 个“插图”。
- 上传、预扫、自动路由和执行支持集合不一致。
- `.ppt` 被路由到只接受 `.pptx` 的工作流。
- PPTX picture shape 与图片化幻灯片没有统一对象状态。
- 语义扫描尚不能对 `ljae439` 输出 5 Figure / 3 Table。
- 格式和内容画像尚未由统一 manifest 正交表达。

默认 pytest 允许预期 XFAIL，但禁止 XPASS；专用命令使用 `--runxfail` 验证红色断言确实失败。红色测试必须具名、绑定后续子计划，禁止无期限的通用 `xfail`。

## 六、任务分解

### Task 1：冻结术语与架构决策

**说明：** 建立仓库首个 ADR，记录格式/画像/处理模式三维解耦、Manifest SSOT、原生/图片化双模式、兼容策略及被拒绝方案。

**验收标准：**

- [x] ADR 包含背景、决策、备选方案、后果、迁移与回滚，状态与 PLAN-030/030a 批准记录一致。
- [x] 契约术语文档对 Figure、Table、physical resource、canvas、occurrence、profile、mode 给出无歧义定义。
- [x] 明确拒绝“扩展名即题材”“候选框即 Figure”“supported 布尔值即运行可用”三种旧模式。

**验证：** 文档链接可解析；ADR/术语中的枚举与 Task 2–4 类型测试一致。

**依赖：** 无。

**可能涉及文件：**

- `docs/decisions/ADR-001-format-profile-manifest.md`
- `docs/contracts/document-structure-manifest-v1.md`

**规模：** S（2 个文件）。

### Task 2：实现 Manifest v1 类型与 Schema

**说明：** 用 Pydantic v2 定义判别联合、字段校验和公开 Protocol，并导出可审阅 JSON Schema；不提供扫描器实现。

**验收标准：**

- [x] 最小及全类型 manifest 可序列化往返，派生 summary、bbox、ID、版本和状态不变量均有测试。
- [x] 未知 major、非法 bbox、重复 ID、矛盾 summary 和无原因失败状态被结构化拒绝。
- [x] 同 major 未知可选字段前向兼容；生成 Schema 与提交文件无漂移。

**验证：** `uv run pytest -q tests/structure/test_manifest_contract.py --no-cov`；`uv run python -m compileall -q qyunslation/structure`。

**依赖：** Task 1。

**可能涉及文件：**

- `qyunslation/structure/__init__.py`
- `qyunslation/structure/models.py`
- `qyunslation/structure/interfaces.py`
- `docs/contracts/document-structure-manifest-v1.schema.json`
- `tests/structure/test_manifest_contract.py`

**规模：** M（5 个文件）。

### Task 3：建立格式能力注册表

**说明：** 将核心、规范化、条件和不支持格式集中到单一注册表；只定义产品要求与探针结果结构，不声称当前机器已经具备能力。

**验收标准：**

- [x] PDF/DOCX/PNG/JPEG/WebP/BMP/TIFF/PPTX 为 CORE，DOC/PPT 为 NORMALIZE，扩展图片格式为 CONDITIONAL。
- [x] 扩展名、MIME、魔数族、允许模式、输出可编辑性与所需 runtime feature 可机读查询。
- [x] 未知格式返回 `UNSUPPORTED_FORMAT`，不回退为 TXT；产品要求和 runtime state 可独立变化。

**验证：** `uv run pytest -q tests/structure/test_format_capabilities.py --no-cov`。

**依赖：** Task 2。

**可能涉及文件：**

- `qyunslation/structure/capabilities.py`
- `tests/structure/test_format_capabilities.py`

**规模：** S（2 个文件）。

### Task 4：建立内容画像注册表

**说明：** 定义首批画像、画像来源和结构先验元数据，证明画像与格式、模式互不替代。

**验收标准：**

- [x] 七个首批画像均可与全部 CORE 格式构造合法决策，不存在扩展名条件分支。
- [x] `AUTO` 画像要求 confidence/evidence；`USER_OVERRIDE` 保留原自动建议但以用户选择为最终值。
- [x] Poster/Presentation 使用 freeform 空间先验，Article/Review 使用阅读顺序和 Figure/Table 先验。

**验证：** `uv run pytest -q tests/structure/test_content_profiles.py --no-cov`。

**依赖：** Task 2。

**可能涉及文件：**

- `qyunslation/structure/profiles.py`
- `tests/structure/test_content_profiles.py`

**规模：** S（2 个文件）。

### Task 5：建立格式×题材金标目录

**说明：** 创建不依赖生产服务的确定性合成夹具清单和 `ljae439` 知识库真值记录；合成夹具带 hash、预期对象和后续所属子计划，知识库夹具带稳定 locator 与导入完整性策略。

**验收标准：**

- [x] 矩阵覆盖 PDF、DOCX、核心图片、PPTX 及 research/review/presentation/poster 关键组合。
- [x] `ljae439.truth.json` 精确列出 Figure 1–5、Table 1–3、正文 scope、知识库 locator；实体导入后要求完整文件 SHA-256。
- [x] 合成夹具可重复生成且内容 hash 稳定；任何缺失必选夹具都会让目录校验失败。

**验证：** `uv run pytest -q tests/structure/test_fixture_catalog.py --no-cov`；连续生成两次比较 hash。

**依赖：** Task 1、Task 2。

**可能涉及文件：**

- `tests/fixtures/structure/catalog.v1.json`
- `tests/fixtures/structure/ljae439.truth.json`
- `tests/fixtures/structure/README.md`
- `tests/fixtures/structure/generate_synthetic.py`
- `tests/structure/test_fixture_catalog.py`

**规模：** M（5 个文件）。

### Task 6：固化当前缺陷为红色行为测试

**说明：** 针对已确认的计数、格式集合、PPT 路由和语义扫描缺口建立严格 XFAIL；同时提供测试辅助层，避免通过解析自然语言日志判定结果。

**验收标准：**

- [x] 每项红色测试绑定唯一 issue code 和负责它转绿的 030b–030g 子计划。
- [x] 默认运行只出现预期 XFAIL、无 SKIP；任一 XPASS 按失败处理并要求立即取消对应 xfail。
- [x] `--runxfail` 当前返回非零，且失败信息直接表达期望契约而非实现细节。

**验证：** `uv run pytest -q tests/structure/test_plan030_red_baselines.py -rxX --no-cov`；再用 `--runxfail` 证明当前失败。

**依赖：** Task 3–5。

**可能涉及文件：**

- `tests/structure/conftest.py`
- `tests/structure/test_plan030_red_baselines.py`

**规模：** S（2 个文件）。

### Task 7：建立单命令阶段门

**说明：** 新增 030a 验证脚本，统一执行 Schema 漂移、契约测试、夹具目录、预期红灯、全量回归和知识库夹具完整性门禁。

**验收标准：**

- [x] 脚本区分 PASS、EXPECTED_RED、BLOCKED、FAIL；BLOCKED/FAIL 均返回非零。
- [x] `ljae439` 缺失知识库 locator 时失败；状态为 `IMPORTED` 却缺失完整 hash 时失败，不使用 sample-missing skip。
- [x] 脚本不依赖 `/home/dev/Hermes`、安装包 `site-packages` 或生产网络。

**验证：** `bash scripts/verify-plan-030a.sh`；删除/篡改临时夹具配置时必须 fail closed。

**依赖：** Task 2–6。

**可能涉及文件：**

- `scripts/verify-plan-030a.sh`

**规模：** XS（1 个文件）。

### Task 8：完成审查记录与后续交接

**说明：** 记录实测命令、Schema hash、夹具 hash、XFAIL 清单和未决风险；只有全部阶段门通过才把 030a 标为完成并允许编写 030b 详细计划。

**验收标准：**

- [x] Walkthrough 包含真实输出摘要，不以“代码存在”代替行为验证。
- [x] PLAN-030/030a 状态、ADR 状态和 xfail owner 一致；没有提前创建 030b 业务实现。
- [x] 工作区差异仅包含 030a 已批准范围，现有全量测试无新增非预期失败。

**验证：** `git diff --check`、`git status --short`、`bash scripts/verify-plan-030a.sh`、`uv run pytest -q`。

**依赖：** Task 7。

**可能涉及文件：**

- `docs/walkthroughs/WT-030a-contract-baselines.md`
- `docs/plans/PLAN-030-semantic-layout-translation/PLAN-030a-cross-format-contract-baselines.md`
- `docs/plans/PLAN-030-semantic-layout-translation/PLAN-030-semantic-layout-translation.md`

**规模：** S（3 个文件）。

## 七、依赖图与执行顺序

```text
Task 1 术语/ADR
   └── Task 2 Manifest v1
         ├── Task 3 格式能力
         ├── Task 4 内容画像
         └── Task 5 金标目录
                └──────────┐
Task 3 ────────────────────┼── Task 6 红色基线
Task 4 ────────────────────┘          │
                                      └── Task 7 单命令门禁
                                                └── Task 8 交接
```

Task 3、Task 4 可在 Task 2 契约冻结后并行；Task 5 可并行准备确定性合成夹具与 `ljae439` 知识库槽位。Task 6–8 必须顺序执行。

## 八、检查点

### Checkpoint A：Task 1–2 后

- ADR、术语、Python 类型与 JSON Schema 一致。
- 最小/全类型 manifest 往返通过，非法版本/ID/bbox/summary 均 fail closed。
- 人工审查 public contract；发现字段语义错误时在此处修正，禁止由后续扫描器倒逼破坏性改名。

### Checkpoint B：Task 3–5 后

- 格式与画像注册表正交，能力与运行状态分离。
- 金标矩阵无必选空洞；合成夹具确定性生成。
- `ljae439` 知识库 locator、精确语义 truth 与实体导入后的 SHA-256 策略已记录。

### Checkpoint C：Task 6–8 后

- 契约测试全绿；红色行为测试全部为预期 XFAIL，无 SKIP/XPASS。
- `--runxfail` 证明当前缺陷仍真实存在，后续子计划有明确转绿责任。
- 全量 pytest 无新增回归，单命令门禁通过，才允许将 030a 标为完成。

## 九、验收命令

```bash
uv run python -m compileall -q qyunslation/structure
uv run pytest -q tests/structure/test_manifest_contract.py --no-cov
uv run pytest -q tests/structure/test_format_capabilities.py --no-cov
uv run pytest -q tests/structure/test_content_profiles.py --no-cov
uv run pytest -q tests/structure/test_fixture_catalog.py --no-cov
uv run pytest -q tests/structure/test_plan030_red_baselines.py -rxX --no-cov
uv run pytest -q --ignore=tests/test_pdf2zh_archive.py --no-cov
uv run pytest -q tests/test_pdf2zh_archive.py --no-cov  # 预期仅 3 个实施前既有失败
bash scripts/verify-plan-030a.sh
```

另执行一次 `test_plan030_red_baselines.py --runxfail`，其当前预期是非零；若返回零，说明缺陷已经转绿或基线失效，必须审查并移除相应 `xfail`，不能机械接受。

## 十、风险与回滚

| 风险 | 处理 |
| --- | --- |
| v1 字段过早冻结 | 030a 只冻结跨模块最小契约；实验性 detector 数据进入 evidence/extensions |
| Pydantic 模型与 JSON Schema 漂移 | Schema 由模型确定性生成并做字节/结构漂移测试 |
| `strict xfail` 变成永久债务 | 每条绑定 owner 子计划和 issue code；XPASS 失败；030i 前不得残留核心 xfail |
| 知识库样本未物化 | 仓内保存 truth、locator 和导入完整性策略；030b/030c 字节级验收前补完整 SHA-256 |
| 新契约影响线上 | 030a 禁止生产接线；删除新增 `qyunslation/structure` 和测试/文档即可完整回滚 |

## 十一、批准记录

用户已批准：

1. 以 Pydantic v2 + JSON Schema 作为 Manifest v1 合同。
2. 使用完整 SHA-256、独立 `object_id/semantic_id`、显式坐标空间和结构化状态/错误码。
3. 将格式能力、运行可用性、内容画像和处理模式建成正交维度。
4. 核心格式、规范化格式和条件图片格式按本计划分级。
5. 用严格 XFAIL 保存 030b–030g 的当前红灯，并禁止样本缺失型假绿。
6. 030a 通过单命令门禁后，才编写 030b 的详细计划。

实施于 2026-09-07 完成；验收证据见 [WT-030a](../../walkthroughs/WT-030a-contract-baselines.md)。下一步仅编写并单独审批 PLAN-030b，不在本子计划中接入生产。
