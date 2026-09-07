# WT-030a：跨格式契约与红色基线实施记录

> 状态：完成
> 日期：2026-09-07
> 计划：[PLAN-030a](../plans/PLAN-030-semantic-layout-translation/PLAN-030a-cross-format-contract-baselines.md)
> 分支：`codex/plan-030a-contract`
> 范围：只新增契约、夹具、测试和阶段门；未接入生产上传/翻译链路，未部署

## 结果

PLAN-030a 已建立后续 030b–030i 共用的 `DocumentStructureManifest v1`、格式能力注册表、内容画像注册表、确定性跨格式夹具和严格红色行为基线。

关键口径已经冻结：

- Figure/Table 主计数按 `type + semantic_scope + semantic_id` 去重，不再把 bitmap、vector、xref 或 shape 数相加。
- 跨页续表或同一语义对象的多次版面出现使用 `semantic_occurrence_index`，每次保留自己的 object ID、canvas 和 bbox，但语义主计数仍为 1。
- PDF、DOCX、PNG、JPEG、WebP、BMP、TIFF、PPTX 为 CORE；DOC/PPT 为 NORMALIZE；SVG/GIF/HEIF/HEIC/AVIF 为 CONDITIONAL；未知格式显式 UNSUPPORTED。
- 文件格式、内容画像、处理模式、输出可编辑性和当前 runtime capability 分开表达。
- Manifest 对文档/资产 hash、canvas/bbox、reading order、题注/子对象关系、输出证据和转换血缘执行 fail-closed 校验。
- 知识库只提供开发/验收样本。真实产品入口仍是用户上传各种受支持资料，生产扫描器、路由器和翻译器不得依赖知识库。

## 交付物

- `qyunslation/structure/models.py`：Manifest v1、判别联合、稳定 ID、语义去重摘要和引用完整性。
- `qyunslation/structure/capabilities.py`：产品格式要求、处理模式、运行依赖与一致性校验。
- `qyunslation/structure/profiles.py`：七种与格式无关的内容画像及 AUTO/USER_OVERRIDE 决策。
- `qyunslation/structure/interfaces.py`：后续扫描器和消费者 Protocol。
- `docs/contracts/document-structure-manifest-v1.schema.json`：可审阅 JSON Schema。
- `tests/fixtures/structure/`：确定性 PDF/DOCX/PNG/JPEG/WebP/BMP/TIFF/PPTX 生成器、目录和 ljae439 真值。
- `tests/structure/test_plan030_red_baselines.py`：6 个严格 XFAIL。
- `scripts/verify-plan-030a.sh`：单命令阶段门，区分 PASS、EXPECTED_RED、BLOCKED、FAIL，并有硬超时。

## 样本矩阵

合成夹具覆盖：单栏研究 PDF、双栏综述 PDF、双栏 DOCX + 原生表 + 共享图片 occurrence、透明 Poster PNG、EXIF 旋转 JPEG、WebP、BMP、双页 TIFF，以及含原生文本/表格/嵌图的 PPTX。生成物不入仓；目录固定每个二进制的 SHA-256，连续生成两次必须完全一致。

`ljae439.truth.json` 固定正文范围 Figure 1–5、Table 1–3。当前 `import_state=PENDING`，通过 `knowledge-base://documents/ljae439.pdf` 预留开发样本；在 030b/030c 进行字节级扫描前，实体导入必须改为 `IMPORTED` 并记录完整 SHA-256。

## 严格红色基线

| issue | owner | 当前可执行证据 |
| --- | --- | --- |
| `QY030-SEM-001` | PLAN-030c | 5 位图 + 2 矢量仍显示为 7 个插图 |
| `QY030-FMT-001` | PLAN-030b | CORE TIFF 被共享预扫描拒绝 |
| `QY030-FMT-002` | PLAN-030b | 未知二进制后缀静默回退 TXT |
| `QY030-NORM-001` | PLAN-030b | `.ppt` 直接进入只接受 `.pptx` 的工作流 |
| `QY030-PPT-001` | PLAN-030g | PPTX picture shape 没有可译对象/执行状态 |
| `QY030-PPT-002` | PLAN-030b | CORE PPTX 不在共享结构预扫描入口 |

所有标记均为 `xfail(strict=True)`。默认测试只允许这 6 个 XFAIL；任一 XPASS 会失败。`--runxfail` 实测为 6 个失败，证明红灯没有被伪造或过期。

## 实测

| 命令 | 结果 |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/structure --no-cov -rxX` | `54 passed, 6 xfailed` |
| `.venv/bin/python -m pytest -q tests/structure/test_plan030_red_baselines.py --runxfail --no-cov` | 预期非零，`6 failed` |
| `.venv/bin/python -m pytest -q --ignore=tests/test_pdf2zh_archive.py --no-cov` | `135 passed, 6 xfailed` |
| `.venv/bin/python -m pytest -q tests/test_pdf2zh_archive.py --no-cov` | 实施前已存在且未变化的 `3 failed` |
| `bash scripts/verify-plan-030a.sh` | `SUMMARY: PASS expected_red=9 blocked=0 fail=0` |
| `git diff --check` | 通过 |

全量测试中的 3 个非 PLAN-030 失败均为既有 archive 文件名口径差异：`test_output_group_key`、`test_infer_original_filename`、`test_ingest_pdf2zh_group_local`。阶段门精确匹配这三个测试；新增或变更失败会导致 FAIL。

## 固定哈希

| 文件 | SHA-256 |
| --- | --- |
| Manifest JSON Schema | `4f77d8427416b11f6a6b0c11f38d77b1625118ca2a6332ff76d17a6a6a3ce128` |
| fixture catalog | `a63b83a067900268fc30c82969533c788fd3df543025cda75b409e671d405ef7` |
| ljae439 truth | `18cb4cc61540d9b2aacb5dbc3ad89faa5414268a52c1716ff460f2454714502a` |

## 最终审查修正

多维审查在阶段门完成前发现并修正了四项问题：

1. 初版一个 semantic ID 只能有一个 bbox，不能表达跨页续表；现已增加 semantic occurrence，并按语义 ID 去重摘要。
2. 初版未完整校验 reading order、题注类型/子对象、output asset 和 conversion lineage 的悬空引用与环；现已全部 fail closed。
3. 初版 fixture/xfail owner 与父计划 030b–030g 的职责编号有偏移；现已逐项对齐。
4. 红色路由测试顶层导入旧 server 模块会污染 FastAPI 测试进程；现改为隔离子进程探测。沙箱中的 TestClient 线程限制也通过正常环境复验排除为代码回归。

## 未决风险与交接

- 030a 有意不接线，因此现有 UI 仍会显示 7 个插图、仍不会完整呈现 Table；这些不是本阶段声称已修复的功能。
- ljae439 实体尚未从知识库物化；030b/030c 字节级验收前必须补完整 SHA-256，不能把 `PENDING` 当扫描通过。
- MIME/魔数探测、Office 规范化、实际 runtime capability probe 属于 PLAN-030b。
- 语义扫描和 5 Figure / 3 Table 转绿属于 PLAN-030c；各格式原位翻译闭环属于 030d–030g。
- 3 个 archive 失败不在 030a 范围内，已作为既有基线保留，未静默忽略新增失败。

下一步只允许编写并审批 PLAN-030b 详细子计划；在批准前不实施输入适配或生产接线。
