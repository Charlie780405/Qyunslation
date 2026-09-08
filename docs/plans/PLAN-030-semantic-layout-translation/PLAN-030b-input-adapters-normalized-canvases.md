# PLAN-030b 子计划：输入适配与归一化画布

> 状态：**已完成**
> 日期：2026-09-07
> 批准记录：用户于 2026-09-07 明确要求“执行 PLAN-030b”
> 父计划：[PLAN-030](./PLAN-030-semantic-layout-translation.md)
> 前置阶段：[PLAN-030a](./PLAN-030a-cross-format-contract-baselines.md)（已完成）
> 阶段边界：只完成输入探测、运行能力、Office 规范化、空画布清单和生产入口接线；不实现 Figure/Table 语义识别、正文翻译或版式回写。

## 一、目标

让任意用户上传文件先经过同一条 fail-closed 输入链路，再进入现有工作流：

1. 不再只信扩展名；联合文件名、声明 MIME 和内容魔数识别格式。
2. PDF、DOCX、PNG、JPEG、WebP、BMP、TIFF、PPTX 进入 CORE 路径。
3. `.doc`、`.ppt` 先经显式 LibreOffice 规范化，再分别进入 DOCX/PPTX 工作流。
4. 未知、伪后缀、损坏、加密、超限和当前环境缺能力的文件在翻译前明确失败。
5. 每个输入生成稳定 SHA-256、资产血缘、运行能力决策和 PDF 页面、DOCX 节、图片帧、PPTX 幻灯片画布。
6. 关闭 PLAN-030a 中属于 030b 的四个严格红灯，同时保留 030c/030g 两个红灯。

## 二、非目标

- 不做题注驱动的 Figure/Table 去重和关联；属于 PLAN-030c。
- 不把画布对象翻译或回写到 PDF/DOCX/图片/PPTX；属于 PLAN-030d–030g。
- 不实现 legacy Office 转换器本身；使用运行环境提供的 LibreOffice/soffice，并显式探测能力。
- 不在 030b 引入 UI 模式选择或发布部署；属于 PLAN-030i。
- 不把知识库变成生产数据源；生产入口始终是用户上传。

## 三、关键设计

### 3.1 探测优先级

内容魔数/容器结构是主证据，扩展名和声明 MIME 是一致性证据：

- 魔数与已知扩展名冲突：`FORMAT_MISMATCH`。
- 魔数与具体声明 MIME 冲突：`MIME_MISMATCH`。
- `application/octet-stream` 只代表未知声明，不覆盖内容判断。
- 无扩展名但内容可识别：按内容接受并补规范化扩展名。
- 内容不可识别且不在既有明确文本格式白名单：`UNSUPPORTED_FORMAT`，禁止回退 TXT。
- ZIP 容器必须通过 OOXML 关键 part 区分 DOCX/PPTX；普通 ZIP 不冒充 Office。

### 3.2 规范化输出

`PreparedDocument` 同时保存：

- 原始文件名、原始格式、原始完整 SHA-256 和输入资产；
- 规范化文件名、格式、字节、完整 SHA-256；
- 规范化资产与 `ConversionStep`；
- `CapabilityDecision` 和空语义对象的 canonical canvases；
- 可序列化审计摘要，但不在日志中输出文件字节、正文或密钥。

未发生格式转换时不得伪造 derived asset 或 conversion step。

### 3.3 画布口径

- PDF：每页一个 `PAGE`，点坐标，保留源旋转。
- DOCX：每个 section 一个 `SECTION`，从 `sectPr/pgSz/cols` 得到页面尺寸与单/双/多栏先验。
- 图片：每帧一个 `PAGE`；EXIF 方向映射到 canonical 宽高；TIFF 必须枚举全部帧。
- PPTX：每张幻灯片一个 `SLIDE`，EMU 转点，布局为 `FREEFORM`。

030b 只建立画布，不创建 BODY/FIGURE/TABLE 等语义对象。

### 3.4 运行能力

能力探针分别报告 `PDF_ENGINE`、`OOXML_ENGINE`、`OFFICE_CONVERTER`、图片解码器、OCR、字体和 slide renderer，不用“依赖名存在”冒充可执行成功。格式策略与运行状态保持正交；请求模式不可满足时在后台任务创建前失败。

### 3.5 兼容接线

- 现有明确文本/表格/字幕/HTML/EPUB 工作流保留。
- PLAN-030 格式必须走字节级探测和准备器。
- 自动路由使用规范化后的格式；手动工作流与实际格式冲突时失败。
- API 继续返回现有 `detail` 字符串形态，并在前缀放稳定错误码，避免破坏前端错误展示。
- 两个主上传端点使用分块读取和统一上限；服务层再次检查，防止 SDK/内部调用绕过。

## 四、威胁模型

| 边界/滥用 | 风险 | 控制 |
| --- | --- | --- |
| 伪造扩展名/MIME | 错路由、解析器混淆 | 内容主证据 + 一致性错误 |
| ZIP bomb/超多 OOXML part | 内存/CPU 耗尽 | entry 数、解压总量、单项和压缩比上限；不解压到用户路径 |
| 超大图片/多帧 TIFF | 内存耗尽 | 文件字节、像素、帧数上限；只做受控解码 |
| 恶意文件名 | 路径穿越、日志污染 | 只保留 basename、去 NUL/控制字符、限制长度；临时文件名固定 |
| 恶意 legacy Office | 外部进程挂死/任意路径输出 | 参数列表调用、隔离临时目录/用户配置、硬超时、输出类型和大小复验 |
| 损坏/加密文件 | 后台伪成功 | 入口 fail-closed，稳定错误码，不创建任务 |
| 敏感正文/密钥泄漏 | 信息披露 | 审计只记录 hash/格式/尺寸；移除 token 前缀日志 |

## 五、任务与依赖

### Task 1：输入探测契约与安全边界

**文件：** `qyunslation/structure/ingest.py`、`qyunslation/structure/__init__.py`、`tests/structure/test_input_detection.py`

**验收：**

- [x] CORE/NORMALIZE/CONDITIONAL 格式可由真实魔数或 OOXML part 识别。
- [x] 扩展名/MIME 冲突、空文件、未知二进制和容器炸弹返回稳定错误码。
- [x] 文件名清洗、完整 SHA-256 和大小边界有测试。

**验证：** 先运行测试证明 RED，再实现并运行 `pytest -q tests/structure/test_input_detection.py --no-cov`。

### Task 2：运行能力探针与模式决策

**依赖：** Task 1

**文件：** `qyunslation/structure/runtime.py`、`qyunslation/structure/__init__.py`、`tests/structure/test_runtime_capabilities.py`

**验收：**

- [x] 每项 RuntimeFeature 有 AVAILABLE/UNAVAILABLE 证据与版本/路径摘要。
- [x] 自动模式只选择当前可满足的模式；请求模式缺能力时显式 UNAVAILABLE。
- [x] DOC/PPT 在无 Office converter 时上传前失败，不静默路由到 OOXML 工作流。

### Task 3：四类 canonical canvas adapter

**依赖：** Task 1

**文件：** `qyunslation/structure/canvases.py`、`tests/structure/test_canvas_adapters.py`

**验收：**

- [x] 合成 PDF、DOCX、核心图片、PPTX 均生成稳定画布。
- [x] 双栏 DOCX、EXIF 旋转 JPEG、双页 TIFF、PPTX slide 数量与尺寸正确。
- [x] 损坏、加密、超像素/超帧输入 fail-closed。

### Checkpoint 1：输入内核

- [x] Tasks 1–3 聚焦测试通过。
- [x] 030a schema/fixture/profile 测试无回归。
- [x] 不依赖网络或知识库运行时路径。

### Task 4：Office DOC/PPT 规范化与资产血缘

**依赖：** Tasks 1–3

**文件：** `qyunslation/converter/office.py`、`qyunslation/converter/doc2docx.py`、`tests/structure/test_office_normalization.py`

**验收：**

- [x] DOC→DOCX、PPT→PPTX 使用同一转换器接口且可注入 fake 测试。
- [x] 命令无 shell、临时路径固定、超时、退出码、缺输出、错误输出和错误格式均被拒绝。
- [x] 转换结果创建 NORMALIZED asset 和无环 lineage，记录转换器版本及参数。

### Task 5：PreparedDocument 纵向准备器

**依赖：** Tasks 2–4

**文件：** `qyunslation/structure/ingest.py`、`tests/structure/test_input_preparation.py`

**验收：**

- [x] CORE 格式返回原字节 + capability + canvases；NORMALIZE 格式返回转换字节 + lineage。
- [x] 无转换时 hash 不变且无伪血缘；转换后输入/输出 hash 可对账。
- [x] 生成可安全记录的审计摘要，正文和原始字节不进入 repr/日志。

### Task 6：共享预扫描接入

**依赖：** Task 5

**文件：** `scripts/doc_image_prescan.py`、`tests/structure/test_plan030_red_baselines.py`、`tests/structure/test_prescan_input_routes.py`

**验收：**

- [x] TIFF 返回 `file_type=image` 并识别多帧；PPTX 返回 `file_type=pptx`。
- [x] DOCX/PPTX 嵌图候选使用 occurrence/part 信息，不把文件级拒绝伪装成零候选。
- [x] `file_sha256` 覆盖完整文件，不再只取前 32 MiB。

### Task 7：生产路由、MIME 与上传上限接线

**依赖：** Tasks 4–6

**文件：** `qyunslation/server/core.py`、`qyunslation/server/uploads.py`、`qyunslation/app.py`、`qyunslation/custom_api.py`、相关测试

**验收：**

- [x] 两个主上传端点传入声明 MIME，并在超限时返回 413。
- [x] 未知输入不再回退 TXT；`.ppt` 不再直接进入 PPTX workflow。
- [x] 自动路由使用规范化格式；任务状态保存不含正文的 ingest 审计摘要。
- [x] 既有明确文本格式和前端字符串错误展示保持兼容；日志不再输出 token 前缀。

### Checkpoint 2：生产入口

- [x] 四个 PLAN-030b 严格 XFAIL 转为普通绿色测试。
- [x] 030c/030g 两个 XFAIL 仍为严格红灯且 `--runxfail` 可证明。
- [x] FastAPI 测试覆盖 413、415/422、伪后缀和合法上传。

### Task 8：真实样本、阶段门和交接文档

**依赖：** Tasks 1–7

**文件：** `tests/fixtures/structure/reference/ljae439.pdf`、truth/catalog、`scripts/verify-plan-030b.sh`、PLAN/WT 文档

**验收：**

- [x] 知识库 ljae439 物化为 TEST_FIXTURE_ONLY，记录完整 SHA-256；生产代码无该路径引用。
- [x] 真实 PDF 得到 10 个稳定 PAGE canvas；语义 5 Figure / 3 Table 仍留给 030c。
- [x] 单命令门区分 PASS、EXPECTED_RED、BLOCKED、FAIL，并精确锁定既有 3 个 archive 失败。
- [x] 全仓无新增失败、工作区干净、walkthrough 记录真实输出。

## 六、阶段验收命令

```bash
.venv/bin/python -m pytest -q tests/structure/test_input_detection.py --no-cov
.venv/bin/python -m pytest -q tests/structure/test_runtime_capabilities.py --no-cov
.venv/bin/python -m pytest -q tests/structure/test_canvas_adapters.py --no-cov
.venv/bin/python -m pytest -q tests/structure/test_office_normalization.py --no-cov
.venv/bin/python -m pytest -q tests/structure/test_input_preparation.py --no-cov
.venv/bin/python -m pytest -q tests/structure/test_prescan_input_routes.py --no-cov
.venv/bin/python -m pytest -q tests/structure --no-cov -rxX
.venv/bin/python -m pytest -q --ignore=tests/test_pdf2zh_archive.py --no-cov
bash scripts/verify-plan-030b.sh
git diff --check
```

## 七、提交切片

1. `docs: approve PLAN-030b input normalization`
2. `feat: detect uploaded document formats safely`
3. `feat: probe runtime format capabilities`
4. `feat: extract normalized document canvases`
5. `feat: normalize legacy office inputs`
6. `feat: prepare uploaded documents with lineage`
7. `feat: route prescan through shared input adapters`
8. `feat: enforce prepared uploads at translation entry`
9. `test: add PLAN-030b verification gate`
10. `docs: complete PLAN-030b walkthrough`

每个切片先测试后提交；若某切片不能独立回滚，继续拆分。

## 八、回滚

- 生产接线提交可独立回滚，恢复旧路由；输入内核和测试仍可保留供后续重接。
- Office 规范化失败不得回退到 `.doc/.ppt` 直进 OOXML workflow。
- 关闭上传准备器时必须显式 feature flag，默认保持 fail-closed，不允许恢复未知格式→TXT。
- 不删除或修改用户原始上传；所有转换只在隔离临时目录进行。

## 九、完成条件

- 所有新增行为先有 RED 证据再转 GREEN。
- 030b 的四个红灯全部转绿，剩余严格 XFAIL 只能是 030c/030g owner。
- 真实 ljae439 与合成格式矩阵通过字节级探测和画布提取。
- 既有 3 个 archive 失败精确不变，除此之外全仓无新增失败。
- 代码审查覆盖正确性、安全、兼容性、性能、可观察性和回滚；无高优先级发现。

实施于 2026-09-07 完成；验收证据见
[WT-030b](../../walkthroughs/WT-030b-input-adapters-normalized-canvases.md)。
下一阶段为单独编写并审批 PLAN-030c，不在本子计划中实现语义 Figure/Table 归并。
