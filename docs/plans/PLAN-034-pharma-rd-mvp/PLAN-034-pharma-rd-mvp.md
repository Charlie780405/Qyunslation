# PLAN-034：医药研发专业翻译平台 MVP（复活）

> 状态：**已批准，文档阶段**（复活空号；本期只写文档，不动业务代码）
> 日期：2026-09-09 批准；2026-09-13 复活落盘
> 前置：PLAN-033l/n 完成（033n @ `76c75cf`）；基线改为 049 之后的 `origin/main`
> 暂停记录：[034可行性评估](../cursor-import/034可行性评估_a94734a0.plan.md)（原标「暂停」）
> 验收门：`bash scripts/verify-plan-034.sh`（文档阶段）
> 分支约定（编码阶段）：`feat/PLAN-034-pharma-rd-mvp`；工作树 `/home/dev/qyunslation-plan-034`（**本期不建**）

## 一句话

英中双向、SaaS 先行、私有部署预留的医药研发专业翻译 MVP：在已建成的 Manifest / 术语 CSV / 确定性排版 / QC 之上，补齐金标契约、Concept 术语库、翻译记忆、模型网关、审校工作台与持久化底座——**不重做 033–049 已交付的保真能力**。

## 编号历史与复活前提

PLAN-034 于 2026-09-09 批准，但**从未落盘**：`docs/plans/` 从 033 直接跳到 035，034 是空号。团队当时转向 035–049 保真线。

| 原前提 | 复活后 |
| --- | --- |
| 033g–033l 完成 | **已满足**（033n 关闭，`verify-plan-033.sh` PASS） |
| 从 PLAN-033 最终提交建工作树 | 从 **`origin/main`（049 之后）** 建；编码阶段再执行 |
| 「现有最高父计划为 PLAN-033」 | 编号序列已到 049；**仍用空号 034**，不改号、不占用 050 |

本期**只写文档**；不建工作树、不改业务代码、不碰 049j 表3 验收线。

## 三态差距矩阵

必须三态区分，否则会重做已交付工作。

### A. 已由 033–049 交付（034 直接引用，不重做）

| 能力 | 证据 |
| --- | --- |
| 参考文献整区 PRESERVE（含章节/文章标题） | 033d + 033h；`PLAN-033-pdf-fidelity.md` 锁定策略 |
| 原始文件与图片永不修改 | 033c（BabelDOC 只吃原稿字节） |
| 原文预览 300 DPI | 033e |
| 模型溯源（model_id + 去凭据 endpoint） | 033g |
| Manifest + 块级执行证据（现 1.2.0） | 033g |
| 图片零截断、role-aware fitter、对象级 QC | 033k |
| 金标样本缺失 → BLOCKED（非 skip） | 033 单文档版 `QYUNSLATION_PLAN033_SAMPLE` |
| 对象存储（本地 + S3/MinIO） | PLAN-013 `StorageBackend` + `MinioStorageBackend` |
| 术语四层治理 370 条 curated | PLAN-039 `governance.py` |
| 占位符保护 / 受控实体 | `protect.py` / `regulatory_entities.py` |
| 确定性排版（不进模型） | `role_fitter` / `table_writeback` |
| 30+ QC 码（含脚注漏译硬失败） | `table_qc` / `image_translate` / `page_qc` |

### B. 有基座，034 做增量

| 基座 | 缺口 → 子计划 |
| --- | --- |
| `TRANSLATE` / `PRESERVE` / `PROTECT_TOKENS` | 缺 `TERM_ONLY` / `HUMAN_REVIEW` → **034b** Manifest 1.3.0 |
| 字重/斜体（033h） | 缺颜色、旋转、对齐、行距完整记录 → **034b** |
| 033 单文档金标 | 扩为三类各 10 份 + Pharma-MQM + 发布阈值 → **034a** |
| Manifest 代码 1.2.0 vs 合同文档写 1.0.0 | 版本 drift 收口 → **034b** |

### C. 真空白（grep 零命中，须新建）

| 空白 | 子计划 |
| --- | --- |
| PostgreSQL / SQLAlchemy / Alembic / OIDC | **034c** |
| Concept 型术语库（同义词/禁用/证据/审批/版本） | **034d**（前置 **034d0** 收敛扁平三分裂） |
| 翻译记忆 / TMX | **034e** |
| 模型网关 + 语义风险分级 | **034f** |
| 人工审校工作台 | **034g** |
| 三类金标端到端 SaaS 试点 | **034h** |

## 依赖链（TM 不得早于持久化）

```text
034a ──► 034b ──┐
                ├──► 034d0 ──► 034d ──► 034e ──┐
034a ──► 034c ──┘         ▲                    ├──► 034f ──► 034g ──► 034h
                          │                    │
                          └── 034c ────────────┘
```

**修正说明：** 把 TM 排在术语桥接之后、持久化之前是错的。精确/模糊 TM 与「仅已批准句段入库」需要关系库（034c）与审校批准（034g）。034d0 是 034d 的前置清理：不先收敛术语三分裂，Concept 迁移会把分裂固化进新 schema。

## 子计划索引

| ID | 文件 | 核心交付 | 依赖 |
| --- | --- | --- | --- |
| 034a | [PLAN-034a-gold-benchmark.md](./PLAN-034a-gold-benchmark.md) | 三类样本目录、Pharma-MQM、基线阈值 | 无 |
| 034b | [PLAN-034b-semantic-policy.md](./PLAN-034b-semantic-policy.md) | Manifest 1.3.0、策略与样式契约 | 034a |
| 034c | [PLAN-034c-saas-persistence.md](./PLAN-034c-saas-persistence.md) | PostgreSQL、租户/项目、审计；复用 StorageBackend | 034a |
| 034d0 | [PLAN-034d0-glossary-ssot-bridge.md](./PLAN-034d0-glossary-ssot-bridge.md) | 术语 SSOT 收敛 + prompt 桥接（**首个编码项**） | 034b、034c（文档可并行；编码前须契约就绪） |
| 034d | [PLAN-034d-concept-termbase.md](./PLAN-034d-concept-termbase.md) | Concept 术语库、审批、CSV/TBX | 034d0 |
| 034e | [PLAN-034e-translation-memory.md](./PLAN-034e-translation-memory.md) | 批准句段 TM、精确/模糊、TMX | 034c、034d |
| 034f | [PLAN-034f-model-gateway-qa.md](./PLAN-034f-model-gateway-qa.md) | 模型网关、风险分级、确定性 QA | 034d、034e |
| 034g | [PLAN-034g-human-review-bench.md](./PLAN-034g-human-review-bench.md) | 逐段审校、批准、术语/TM 闭环 | 034c、034f |
| 034h | [PLAN-034h-gold-saas-pilot.md](./PLAN-034h-gold-saas-pilot.md) | 端到端门禁、PWA、OIDC、部署回滚 | 034a–034g |

## 锁定的产品决策（不再讨论）

1. 首期语言：英语 ↔ 简体中文双向。
2. 产品形态：响应式 Web/PWA + 版本化 API（`/api/v1`；保留 `/service` 兼容层）。
3. 部署：SaaS 优先；存储、模型、身份接口预留私有部署适配。
4. 金标文档三类：(1) 科研文献与综述；(2) 临床试验方案、IB、CSR；(3) CTD Module 2 总结。
5. PDF / DOCX / PPTX / XLSX / 图片可上传；非金标场景明确显示 Beta。
6. 不训练基础模型；`qwen3.6:35b-a3b` 仅作基线，经模型网关解耦。
7. 必须建设 Concept 术语库、翻译记忆与人工批准闭环。
8. 参考文献整区（含章节标题与文章标题）原样保留。
9. 原始文件与图片永不修改；译文是可追溯派生对象。
10. **不属于本计划**：App、小程序、计费、公开打包 MedDRA、全研发文档同等级保证。

## 明确否决（吸收开源路线报告后）

- 用 Docling / DocLayout-YOLO / PaddleOCR **替换**现有结构 Manifest 生产链（Docling 已在仓但 `CONVERT_ENGINE=identity`；DocLayout 有实测否决；PaddleOCR 生态位已被 RapidOCR + HPD 占满）。
- NLLB-200 / LibreTranslate / Argos 进入医药主流程。
- 把排版能力训练进模型；模型只负责内容翻译与必要语义判断。
- 快速通道 OPUS-MT + CTranslate2：当前瓶颈是质量闭环不是速度，**暂缓**。

## Out of Scope（本期文档阶段）

- 任何业务代码、数据库迁移、依赖安装
- 创建 `feat/PLAN-034-pharma-rd-mvp` 工作树/分支
- 动 049j 表3 / 重译验收线
- 新建 Skill（等 034d0 实现后再沉淀踩坑）

## 验收门槛（产品级，编码阶段适用；文档阶段以 verify 脚本为准）

- 三类金标各 ≥10 份；只记目录、标签、哈希，不提交真实资料；缺样本 → BLOCKED。
- 金标产物无未解决 Critical 医药错误；硬性术语命中率 ≥98%；禁用译法 = 0。
- 数字、单位、DOI、引用编号、参考文献保护通过率 100%。
- 原始文件与图片哈希不变；Figure/Table/脚注无遗漏；表格行列语义不变。
- 标题与表格粗体继承正确；同角色字号一致；图片与表格零截断零溢出。
- 现有 PLAN-028、029、030e、033 总门全部通过。
- 任一 FAIL 或 BLOCKED 不得宣称 PLAN-034 完成。

## 提交约定（编码阶段）

1. `docs: approve PLAN-034 pharma translation MVP`（文档阶段本批）
2. `test: establish PLAN-034a pharma gold benchmark`
3. 034b–034g 按子计划分别实施、验证、原子提交
4. `test: add PLAN-034h end-to-end SaaS gate`
5. `docs: complete PLAN-034 walkthrough`

精确 `git add`；不覆盖式批量提交；不直接合并或推送 `main`（功能分支推送为远端保存点）。

## 完成定义（文档阶段）

- [x] 纲领含编号历史、三态矩阵、依赖链、子计划索引
- [x] 034a–034h + 034d0 齐备
- [x] `scripts/verify-plan-034.sh` PASS
- [x] 可行性评估标注已复活；`docs/plans/README.md` 索引更新
