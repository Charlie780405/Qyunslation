# PLAN-080：PDF 译文完整性、字体统一、装饰线随文与人名职务保留

> 状态：**v5，080a–080h 全部实现并已部署（2026-10-20，用户执行），保留策略的修复已在生产生效；字体策略、装饰线随文、段落级 QA、Office 保留四个开关默认关闭，灰度见 [runbook](../../runbooks/plan-080-rollout.md)；部署后的第二轮补缺（参考文献、Office、字体策略目标语言、多样本标定等）见 WT-080 §6**（实施记录见 [WT-080](../../walkthroughs/WT-080-pdf-translation-completeness-and-typography.md)）
> 日期：2026-10-20
> 范围：文字型 PDF（BabelDOC / pdf2zh-next 通道）的译文质量规则，覆盖所有内容画像（GENERIC / REGULATORY / RESEARCH / REVIEW），不只服务当前样本
> 前置：[PLAN-041](../PLAN-041-pdf-regulatory-form-fidelity/)、[PLAN-042](../PLAN-042-regulatory-translation-quality/)（受控实体 042e）、[PLAN-044](../PLAN-044-regulatory-layout-normalize/)（字号归一）、[PLAN-047](../PLAN-047-delivery-loop-fidelity/)（never-drop、capture）、[PLAN-074](../PLAN-074-author-terms-qa/)（作者与单位原文保护）
> Skill：SK-Q003 `pdf-regulatory-form-fidelity`、SK-Q005 `babeldoc-patch-safety`、SK-Q006 `literature-paragraph-layout`、SK-Q007 `translation-content-integrity`、SK-Q004 `translate-stack-process-boundary`、SK-Q008 `translation-pitfall-capture`
> 验收：`bash scripts/verify-plan-080.sh`（PASS / FAIL / BLOCKED，BLOCKED 不计为通过）；证据 `docs/walkthroughs/WT-080-*.md`（实施时新建）

> **v2 修订（2026-10-20，用户确认后）**：①D1–D5 决策落定，见 §8；②规则 C1–C4 的适用范围由“GENERIC/REGULATORY”改为“所有内容画像”（§3 目标 1、§4）；③译文字体固定为思源宋体（SourceHanSerifCN），不再以霞鹜文楷为候选（§5 080c）；④080a 的完成标准增加“按画像分组”的基线。

## 1. 触发与证据

用户对一份 FDA 会议纪要的中文译文（28 页，EN→ZH）提出四类质量问题。样本是 job `d8faef9f…` 下 run `e5be0956…` generation-2 的 mono 输出，源 PDF 在 `var/pipeline/runs/e5be0956…/gen-2/input/`。**样本文件不入库**，走环境变量 `QYUNSLATION_PLAN080_SAMPLE`（沿用 041/044 的约定）。

| # | 用户反馈 | 本机证据（只读检查，PyMuPDF） |
| --- | --- | --- |
| 1 | 大段落没有翻译（背景、统计问题等） | 输出中残留的拉丁字母数 / 源文拉丁字母数：第 16–19 页约 51% / 44% / 30% / 44%，第 1–3 页约 34% / 60% / 61%（第 5–14 页约 4–14%；该比值含合法保留的人名、URL、引用标题，只作粗略对比）；第 16 页整页 `Arial-ItalicMT` 原样保留。**但运行日志写 `Total: 249, Successful: 246, Fallback: 3`，没有失败告警**，即这些段落多数根本没进入翻译，不是翻译失败 |
| 2 | 译文字体前后不一致 | 同一份输出同时使用 `SourceHanSerifCN-Regular/Bold`、`LXGWWenKaiGB-Regular`、`NotoSerif-Regular/Italic/Bold`、`ArialMT`、`Arial-ItalicMT`、`Calibri`；字号 8–12pt 混用。第 4–14 页以霞鹜文楷为主，第 13 页换成思源宋体，第 15–19 页又变回 Arial 斜体 |
| 3 | 下划线/标记照抄原文位置，超出实际文字 | 源 PDF 的下划线是独立矢量线（如第 4 页 `(72,278) 宽 66pt 高 0`），输出同页薄线数量与源一致。BabelDOC 重排译文后只改文字不改图形，线条仍按**英文原文宽度与位置**绘制 |
| 4 | 人员、职务等可不译 | 参会人名单、签字栏的职务在输出里有的保留英文、有的被译、字体各异（第 2–3 页有长职务串未译，同表另有中文职务） |

> 本计划**不**声称已定位到漏译的单一根因。§2 把已核实的事实和待验证的假设分开写，由 080a 先做逐段诊断，再决定 080b 的修法。

## 2. 根因分析

### 2.1 已核实

- **R1 漏译发生在翻译之前**：日志统计的是已送入 LLM 的段落。未送入的段落（被判为公式/被过滤/未成段）不会出现在 Fallback 里，所以现有 verify 的 `Fallback` 计数（SK-Q007 铁律 1）对这类漏译是盲的。
- **R2 BabelDOC 的公式字体默认模式含 `Arial.*`、`Calibri.*`、`TimesNewRoman.*`**（`babeldoc/format/pdf/document_il/utils/formular_helper.py` 的 `is_formulas_font`）。**080a 已证伪其为主因**：Arial 斜体段落 73 段中 70 段已译出，见 §2.3。
- **R3 字体混用来自引擎的“按样式选字体”**：粗体、斜体、衬线、拉丁字符回落分别映射到不同字体，项目侧没有任何统一策略（`runner.py` 只传了 CLI 开关，没有字体设置）。
- **R4 BabelDOC 只重写文字，不重写矢量图形**：下划线、框线、删除线、高亮块都留在原坐标。

### 2.2 待验证（080a 负责证实或证伪）

| 编号 | 假设 | 判据 |
| --- | --- | --- |
| H1 | 整页斜体或 Arial 系字体被公式字体模式吞掉，段落被整体视为公式字符而不送翻译 | **已证伪（080a）**：Arial 斜体 73 段中 70 段已译出（WT-080 §2.1） |
| H2 | 页眉页脚、列表、带项目符号的段落被段落切分成碎片，低于 `min_text_length` 被跳过 | **未观察到**（080a 未发现因长度跳过的正文段；`min_text_length` 不是主因） |
| H3 | 版面检测（DocLayout-YOLO）把正文区误判成非正文类别 | 未单独验证；080a 的根因已能解释全部漏译段，暂不需要 |
| H4 | 本样本被判为 `GENERIC`（置信度 0.4），没有走任何监管/文献专属修复 | **已确认**：manifest 中 `content_profile=GENERIC`，`profile_confidence=0.4` |
| H5 | 下划线偏长是因为原线按英文宽度，且译文换行后文字更短，而不是线被画错 | **部分确认（080a）**：7 条中文行下划线超过文字宽度 1.3 倍（最长 2.13 倍，短标题）；另有 17 条线悬空（源文 5 条）。"所有下划线过长"不成立，C3 需同时处理过长与悬空 |

### 2.3 080a 结论（2026-10-20，基线见 WT-080 §2–3）

只读诊断与源码核对后，漏译的根因是三个**规则缺陷**，而不是公式字体：

| 编号 | 根因 | 证据 | 状态 |
| --- | --- | --- | --- |
| M1 | `paragraph_is_preserved` 把任何位置的编号段落（"2. …"、"1 We update…"）当作参考文献条目，送 LLM 之前即保留，不写日志 | 直接调用：`2. The protocol synopsis…` 返回 True，与门控状态无关；既有测试设计要求编号条目只在参考文献区内生效 | **已修复**（`babeldoc_policy.py`），有单元测试 |
| M2 | 前置信息分类误判正文长句：`Co., Ltd.` 等机构标记加上不在动词表中的正文句 → AFFILIATION；邮箱加人名 → AUTHOR。第 3 页"背景"段即此类 | 直接调用：`classify_frontmatter_text` 对 303 字背景段返回 `affiliation`；第 18–20 页长段返回 `explicit author marker` | **已修复**（`frontmatter.py`：机构句 ≤30 词；作者邮箱/corresponding 需非正文句），有单元测试 |
| M3 | 模型原样返回，BabelDOC 的 "same as input" 回退后保留源文 | 追踪（WT-080 §2.2）：`Fallback: 3` 对应三条 **URL 脚注**，原样返回合理；旧译文中的正文漏译均由 M1/M2 造成 | **已追踪，结论：不造成正文漏译，不需要重试机制** |

另外两个结论：
- 逐段统计中，长段落的保留率与长度无关（≥600 字段大多译出），所以不是"长段落超限"。
- 本样本中原样保留的段落，有 8 个是非名单类正文（第 3、15、16、17、18、19 页），与用户反馈的"背景"和"统计问题"两处吻合。

## 3. 目标与非目标

**目标（对同类文档生效，不只样本）**

1. **完整性**：任何文字型 PDF，译后不允许存在“应译而原样保留”的整段正文。不译只能是有名有据的保留（人名、职务、编号、URL、受控实体），每一处都能说出原因。
2. **字体统一**：同一文档的译文正文只出现有限、可预期的字体族，字号层级少；粗/斜体用同族变体表达。
3. **装饰线随文**：下划线、删除线、框线等与文字绑定的矢量线，按译文实际外接框重画；无法确定归属的线保持原样，不误删。
4. **人名与职务保留**：人名和职务/部门/机构名按统一规则原样保留并统一字体，不出现同表一半译一半不译。
5. **可观测**：QA/verify 能自己发现“漏译”“字体过多”“线条悬空”，不靠用户截图。

**非目标**

- 不改翻译模型与提示词的整体策略（PLAN-071/076 范围）。
- 不做扫描件/图片内文字（SK-Q001/Q002）与表格内部（SK-Q009）的新规则，只保证本计划不破坏它们。
- 不要求译文与原文字体一致，只要求译文自身一致。
- 不做词/句级装饰线（波浪线、高亮渐变）以外的复杂图形重建。

## 4. 项目规则（落入 skill，替换“逐文件修”的做法）

这四条是本计划最终要写进 skill 的规则；每条带“症状 / 先查 / 修法 / 判据”，符合 SK-Q008 的铁律格式。

| 规则 | 内容 | 判据 |
| --- | --- | --- |
| **C1 译文完整性** | 译前先对源 PDF 做**段落台账**：每个文本块有 `translate / keep(reason)` 两种去向，禁止第三种“静默不管”。译后按台账核对：`translate` 项的输出不得与源文相同。`keep` 的 reason 取自固定枚举（`PERSON_NAME`、`JOB_TITLE`、`ORG_NAME`、`URL_EMAIL`、`IDENTIFIER`、`FORMULA`、`USER_PRESERVE`） | 台账中 `translate` 且未变的段数 = 0；每个 `keep` 有 reason |
| **C2 字体策略** | 译文字体由项目统一指定：正文一个中文字体族 + 一个拉丁回落字体；粗/斜体用同族的 Bold / 合成斜体；字号层级 ≤ 3（正文、小字、标题）。不再随原文 Arial/Times/Calibri 变化 | 非页码页眉的译文页面 `(字体族, 字号)` 种类 ≤ 阈值（初定 4，由 080a 基线校准） |
| **C3 装饰线随文** | 源 PDF 中紧贴文本行下沿（或穿过中线）、宽度≈文字宽度的水平线，视为文字装饰（下划线/删除线），译后按对应译文行的实际外接框重画；线与文字的对应关系写入台账 | 样本中每条下划线的宽度与对应译文文字宽度之差 ≤ 容差（初定 1 字宽），无悬空线 |
| **C4 人名与职务** | 人名、职务、部门、机构名走“保留原文 + 统一字体”：命中受控实体词表或名单/签字栏结构（如两栏表中“姓名 – 职务”）即保留；不让模型自由决定译不译 | 同一名单内保留/翻译不混用；名单区域字体一种 |

## 5. 工作包

执行顺序 080a → 080b → 080c/080d（可并行）→ 080e → 080f → 080g。

| ID | 内容 | 主要文件 | 优先级 | 估算（人日） |
| --- | --- | --- | --- | --- |
| 080a | **逐段诊断与基线**（只读）：对样本及 ≥3 份不同类型的 PDF（真实药监信函、文献、普通商务文档）dump 段落台账：每段的源文、是否送翻译、跳过原因、公式字符占比、字体、版面类别、译后是否变化；统计字体种类与装饰线（含线与文字的对应）。证实/证伪 H1–H5 | 新增 `scripts/qa/plan080_diagnose.py`；输出 `var/plan080/`（不入库） | P0 | 1–1.5 |
| 080b | **完整性修复（C1）**。v3 修订：不再收窄公式字体（H1 已证伪）。已完成：M1（编号段落只在参考文献区内保留）、M2（机构句 ≤30 词；作者邮箱需非正文句），均在仓库代码中生效（`PYTHONPATH` 指向仓库，见 WT-080 §4），有单元测试，并经一次样本重译验证（WT-080 §5.1：非名单长保留段 8→1，第 16 页拉丁字母 1151→72）。M3 已追踪并关闭（不需要重试）。工具：`scripts/qa/plan080_trace_run.py`（包装 BabelDOC 记录每段去向，不改引擎文件）与 `plan080_trace_report.py`。待办：`_QY_033H_PRESERVE` 的静默 `except: return False` 改为告警（需改补丁脚本并重启 pdf2zh，未做） | `qyunslation/structure/babeldoc_policy.py`、`qyunslation/structure/frontmatter.py`、`tests/structure/test_plan080_preserve_policy.py`、`scripts/qa/plan080_trace_*.py` | P0 | 已完成约 2；静默失败告警另估 0.25 |
| 080c | **字体统一（C2）**。已实现（默认关闭）：`FontMapper.map` 包装，开启后译文只用 SourceHanSerifCN Regular/Bold（画像写 sans-serif 时用思源黑体），不按斜体换字体；开关 `QYUNSLATION_FONT_POLICY`；样本每页字体种类最大 10→5、中位数 6→4。被保留的原文不经过 `FontMapper`，其字体统一归 080e。字号层级归一未做（样本字号 8/10/11/12/15，非本次反馈重点） | `qyunslation/structure/font_policy.py`、`scripts/apply-pdf2zh-080c-fonts.py`、`tests/structure/test_plan080_font_policy.py`、`tests/scripts/test_plan080c_font_patch.py` | P0 | 已完成约 1.5 |
| 080d | **装饰线随文（C3）**。已实现（默认关闭）：源页确认文字装饰线（贴行下沿、不宽于文字、非表格线），译文页按实际文字范围裁短／挪位／删除，涂抹只允许触碰线自身；runner 在 CLI 成功后调用，开关 `QYUNSLATION_DECORATION_REALIGN`；mono 与 dual 都处理。样本：过长 7→0，悬空 18→5（余下为源文原有分隔线），文字内容不变。限制：无法精确到词（小标题线只保证不超出所在行）；只处理水平细线 | `qyunslation/structure/decoration_realign.py`、`qyunslation/workbench/runner.py`、`tests/structure/test_plan080_decoration_realign.py`、`tests/workbench/test_plan080d_runner_hook.py` | P0 | 已完成约 2 |
| 080e | **人名与职务保留（C4）**。已实现：`entity_preserve.is_job_title` 保守识别职务并接入保留策略，`preserve_reason` 给出 `PERSON_NAME`/`JOB_TITLE`/`ORG_NAME`；重放样本新增保留 25 条，全是职务。不做纯人名规则（与标题无法区分）；被保留原文保持源字体（有意，见 WT-080 §5.4）；同时修了机构/作者误判的功能词线索遗漏 | `qyunslation/structure/entity_preserve.py`、`qyunslation/structure/babeldoc_policy.py`、`qyunslation/structure/frontmatter.py`、`tests/structure/test_plan080_entity_preserve.py` | P1 | 已完成约 1 |
| 080f | **QA 与门禁**。已实现（默认关闭，只出警告）：`pdf_layout.check_output_layout`，三个新警告码 `UNTRANSLATED_PARAGRAPH`、`FONT_FAMILY_SPRAWL`、`DECORATION_DANGLING`（已存在的 `UNTRANSLATED_BODY` 是整页占比的 C1，不复用）；样本五个版本验证：旧译文命中 8 个漏译段，修复后不再命中 | `qyunslation/pipeline/qa/pdf_layout.py`、`qyunslation/pipeline/qa/registry.py`、`qyunslation/pipeline/qa/pdf_inspect.py`、`tests/pipeline/test_plan080f_layout_qa.py` | P1 | 已完成约 1.5 |
| 080g | **回归、验证脚本、skill 与台账沉淀**。已完成：`scripts/verify-plan-080.sh`、SK-Q003/Q005/Q007、`error-signatures.toml`、registry 审计行、WT-080 | `scripts/verify-plan-080.sh`、`.cursor/skills/**` | P1 | 已完成约 1 |

| 080h | **Manifest 2.0 遗留的 3 个测试失败与 schema 合同收口**（独立子计划，见 [PLAN-080h](./PLAN-080h-manifest-schema-test-baseline.md)）：失败与 PLAN-080 无关，但会污染本计划的验证基线；其中 `manifest_view` 拒绝 major 2 是一个真实的产品缺陷 | `tests/structure/test_manifest_*.py`、`qyunslation/ui/manifest_view.py`、`docs/contracts/document-structure-manifest-v1.schema.json` | P2 | 0.5–1 |

| 080i | **部署后的第二轮补缺**：参考文献不依赖标题与段落顺序（`is_citation_entry`/`is_citation_block`，新 QA `REFERENCE_ENTRIES_CHANGED`）、保留谓词静默失败告警、页数不一致时装饰线跳过、字体策略默认思源宋体且只对简体中文目标生效、Word/PPT 保留规则（`QYUNSLATION_OFFICE_PRESERVE`）、中译英保护测试、runner 端到端与真实 FontMapper 测试、4 份文档的多样本标定、灰度 runbook | 见 WT-080 §6 | P0 | 已完成约 3 |

合计约 14.5–20 人日（含 080h、080i），未经排期。

### 080a 的硬要求

- 只读，不改生产数据，不读取 `.env`。
- 样本不够时标“未知”，不据此改阈值（沿用 PLAN-079 阶段 B 的做法）。
- 产出必须回答：**漏译段落是“没送翻译”还是“送了但结果等于源文”**，以及各自的比例；这决定 080b 的改法。

### 080b/080c/080d 共同的实现约束

- 引擎补丁失败的模式必须是“难看”而不是“消失”（SK-Q005 诊断三问）；任何补丁配 never-drop 兜底。
- 改 `scripts/apply-pdf2zh-*.py` / `doc_profile.py` 必须重启 `pdf2zh.service`，改 `qyunslation/extensions/**` 必须重启 `qyunslation-office.service`，统一走 `bash scripts/deploy-translate-stack.sh`；验证“改了没效果”时先比对进程启动时间与文件 mtime（SK-Q004）。本地环境此前找不到 `pdf2zh.service` 单元（PLAN-079 F6），部署验证由用户在有权限的环境执行，本计划不假设已部署。
- 后处理失败要降级为“保留上游输出 + 告警”，不能让交付失败。
- 新规则全部带开关（环境变量或画像配置），默认值见 §8 的 D3。

## 6. 验证

- **单元/夹具**：合成 PDF（含编号问题段、含公司名的长句、名单、带下划线标题），断言台账、字体种类、线宽对应。
- **实样**：`QYUNSLATION_PLAN080_SAMPLE` 指向样本源 PDF，重译后跑 080a 的诊断脚本，对比前后：`translate` 未变段数、字体种类、下划线宽度差。
- **门禁脚本**：`scripts/verify-plan-080.sh`，PASS / FAIL / BLOCKED 三态；没有样本、没有浏览器、没有部署权限时标 BLOCKED，不当作通过。
- **回归**：`tests/structure`（慢，约 6 分钟）、`tests/pipeline`、`tests/api`；既有 `verify-plan-041`…`049` 不得退化。
- **目视核对**：对照视图并排看 4 类问题页（样本第 1–3、4、16–19 页），记入 WT-080；这一步无法自动化。

## 7. 沉淀与文档同步（工作区规则要求）

| 产物 | 内容 |
| --- | --- |
| `.cursor/skills/pdf-regulatory-form-fidelity/SKILL.md` | 增补 C1 台账、C4 名单规则（与 SK-Q003 的受控实体条并列，适用所有内容画像的正文，不限表格）；增补症状行："编号问题/背景段整段英文"→ 先查保留谓词 |
| `.cursor/skills/babeldoc-patch-safety/SKILL.md` | 增补：①保留谓词（`_QY_033H_PRESERVE`）是**静默跳过**，不写日志，verify 的 Fallback 计数看不到；②`paragraph_is_preserved` 必须与 `filter_paragraphs_for_llm` 使用同一套状态逻辑；③导入 `qyunslation` 失败时该谓词静默返回 False；④诊断顺序：先用 `plan080_trace_run.py` 看段落去向，再猜原因 |
| `.cursor/skills/translation-content-integrity/SKILL.md` | 修正铁律 1：`Fallback` 计数只覆盖已送翻译的段，另加台账核对 |
| `.cursor/skills/skill-registry/error-signatures.toml` | 新增签名：`SIG-UNTRANSLATED-BODY`、`SIG-FONT-SPRAWL`、`SIG-DECORATION-DANGLING`，各带 first_check / fix / verify |
| `.cursor/skills/skill-registry/registry.md` | 审计表加一行（PLAN-080） |
| `docs/plans/README.md` | 登记 PLAN-080，下一编号改为 PLAN-081 |
| `docs/walkthroughs/WT-080-*.md` | 实施后新建，含基线数据与前后对比 |

是否新建独立 skill：**不新建**。四条规则分别落在现有 SK-Q003/Q005/Q007，避免出现第二个“PDF 保真”归属（SK-Q008 通用原则 3：一个坑只有一个 canonical 归属）。

## 8. 决策（2026-10-20 用户确认：D1、D2 按用户选择；D3–D5 按推荐项执行，有问题再修改）

| 编号 | 问题 | 选项 | 推荐 |
| --- | --- | --- | --- |
| D1 | “人员和职务可不译”的范围 | a. 人名 + 职务 + 部门 + 机构名全部保留英文；b. 只保留人名，职务与部门译成中文 | **已确认 a**（用户：人名、职务、部门、机构名可以不译）。原理由：与你的反馈一致，且名单里的职务串很长、译文易换行失真。注意：这会让译文里留有成片英文，需要在 QA 中把它们标为“有意保留”，不计入漏译 |
| D2 | 译文中文字体选哪个 | a. 思源宋体（SourceHanSerifCN，现样本已在用）；b. 霞鹜文楷（现样本主体字体，偏手写风）；c. 沿用原文风格（现状，不统一） | **已确认 a**（用户选择思源宋体）。原理由：监管/药监文件更适合宋体；文楷不适合正式文件。字体文件是否已随栈部署由 080c 先核实 |
| D3 | 新规则默认开关 | a. 默认关闭，灰度后切换；b. 默认开启 | **已确认 a**（按推荐执行，有问题再改）：先影子运行（只出报告不改输出），样本与回归稳定后再开启，回滚只需关开关 |
| D4 | `UNTRANSLATED_BODY` 初期是警告还是阻断 | a. 先警告；b. 直接阻断（C1） | **已确认 a**（按推荐执行，有问题再改）：080a 之前不知道误报率；待基线稳定再升级 |
| D5 | 是否把规则推广到文献（RESEARCH/REVIEW）与 GENERIC | a. 全画像；b. 先 GENERIC + REGULATORY | **已确认 a**：规则适用于所有内容画像，不限 GENERIC/REGULATORY。文献路径有 SK-Q006 的既有段落重排，改动前必须过既有 `verify-plan-045/046` |

## 9. 风险

| 风险 | 影响 | 控制 |
| --- | --- | --- |
| 保留策略收紧后，真正的参考文献、作者行被送去翻译 | 参考文献条目或署名被改写 | `[n]` 形式与参考文献区内的编号条目仍保留；作者行只放宽长正文句，ORCID 与短署名不变；既有 PLAN-033h/045/074 测试全部保留并通过；样本重放核对被保留段落清单 |
| 字体统一后缺字形（罕见字、上下标） | 出现方块字 | 回落字体链 + 缺字形计数写入 QA；不删字 |
| 线条重画误改表格线、分隔线 | 版面破坏 | 只处理“紧贴文本行下沿且宽度≈文字宽度”的线；归属不明保持原样；夹具含表格线反例 |
| 保留职务英文导致“漏译”误报 | QA 噪声 | 台账 `keep(reason)` 单独计数，不计入 `UNTRANSLATED_BODY` |
| 后处理增加耗时 | 交付变慢 | 只处理有命中的页；影子阶段记录耗时 |
| 补丁与 BabelDOC 版本漂移 | 升级后失效 | 沿用补丁标记清单；`already patched` 但行为是旧的先查标记（SK-Q011） |

## 10. 当前限制

- 080a 只读诊断已完成（WT-080 §2–3）。**没有重译，没有渲染页面目视核对，没有读 `.env` 或生产库**。080b 的 M1/M2 修复经单元测试、样本重放和一次完整重译验证；尚未渲染页面目视核对。
- 样本重译只做了一次，且使用运营配置的默认值（无生产服务的模型快照、自定义提示词和环境变量），LLM 有随机性；前后对比不是严格对照（WT-080 §5.1）。
- 下划线的"过长"与"悬空"只在样本上统计，其他文档的分布未知。
- 估算未经排期，阈值（字体种类 ≤4、线宽容差）是初值，须由 080a 基线校准。
- 本机找不到 `pdf2zh.service` 单元（见 PLAN-079 F6），补丁部署与重启需用户配合。
