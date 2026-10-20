# WT-080：PDF 译文完整性、字体统一、装饰线随文与人名职务保留（080a 诊断与 080b 首批修复）

日期：2026-10-20  
纲领：[PLAN-080](../plans/PLAN-080-pdf-translation-completeness-and-typography/PLAN-080-pdf-translation-completeness-and-typography.md)（v2，决策 D1–D5 已确认）

## 1. 本轮做了什么

| 编号 | 状态 | 说明 |
| --- | --- | --- |
| 080a 逐段诊断 | 已完成（只读） | `scripts/qa/plan080_diagnose.py`；结果 `var/plan080/pind-e5be-gen2-mono.json`（不入库） |
| 080b 完整性（首批） | 已修复两处根因，有单元测试；**已部署到生产服务（2026-10-20，见 §8）**；尚未用真实生产作业复验 | `qyunslation/structure/babeldoc_policy.py`、`qyunslation/structure/frontmatter.py` |
| 080b 段落追踪（M3） | 已完成，结论：M3 不造成正文漏译（见 §2.2） | `scripts/qa/plan080_trace_run.py`、`scripts/qa/plan080_trace_report.py` |
| 080h manifest 测试基线 | **已完成**：全量 956 passed、0 failed | [PLAN-080h](../plans/PLAN-080-pdf-translation-completeness-and-typography/PLAN-080h-manifest-schema-test-baseline.md) |
| 080c 字体统一 | **已实现并已部署（补丁已写入引擎），开关默认关闭**（见 §5.2、§6） | `qyunslation/structure/font_policy.py`、`scripts/apply-pdf2zh-080c-fonts.py` |
| 080d 装饰线随文 | **已实现并已部署，开关默认关闭**（见 §5.3、§6） | `qyunslation/structure/decoration_realign.py`、`qyunslation/workbench/runner.py` 钩子 |
| 080e 人名职务保留 | **已实现**（见 §5.4）；默认开启（是保留策略的一部分） | `qyunslation/structure/entity_preserve.py`、`babeldoc_policy.py` |
| 080f 段落级 QA | **已实现，默认关闭**（见 §5.5） | `qyunslation/pipeline/qa/pdf_layout.py`、注册表 3 个新警告码 |
| 080g 回归与沉淀 | **已完成**（见 §5.6） | `scripts/verify-plan-080.sh`、skill、签名表 |

## 2. 080a 基线（样本：job `d8faef9f…` / run `e5be0956…` / generation-2 mono，28 页，manifest 判为 `GENERIC`，置信度 0.4）

| 指标 | 值 | 说明 |
| --- | --- | --- |
| 长段落（≥40 字符、无汉字） | 172 | 诊断脚本的 `src_long_blocks` |
| 译文中逐字保留的长段落 | 41 | 其中 28 个是人名、职务、抬头、地址等（D1 保留范围） |
| 译文中逐字保留的**非名单**长段落 | 13 | 见 §2.2 |
| 源文下划线（水平细线）匹配到文本行 | 69（悬空 5） | 源文中英文行的线宽 / 文字宽度 中位数 0.59 |
| 译文中文行下划线 | 47 匹配，悬空 17 | 中位数 0.79；**超过 1.3 倍的 7 条**，最长 2.13 倍（"补充意见："） |
| 译文中英文行下划线超限 | 0 / 10 | |
| 每页正文字体种类（字号 ≥7pt） | 最多 10 种 | 出现过的族：SourceHanSerifCN Regular/Bold、LXGWWenKaiGB、NotoSerif Regular/Italic/Bold、ArialMT、Arial-ItalicMT、Arial-BoldMT、Calibri |
| 运行日志 | `Total 249, Successful 246, Fallback 3` | Fallback 的三条都是 "Translation result is the same as input, fallback" |

### 2.1 H1（公式字体模式吞掉 Arial 段落）：不成立

按完整字体名统计源段落的保留率：

| 源字体 | 段数 | 逐字保留 |
| --- | --- | --- |
| Arial/ItalicMT @12 | 73 | 3 |
| ArialMT @12 | 44 | 7 |
| Arial/BoldMT @12 | 24 | 0 |

即 Arial 斜体段落绝大多数已被译出，"整族 Arial 被当公式吞掉"与数据不符。PLAN-080 §2.1 的 R2 只说明公式字体模式含 `Arial.*`，不能据此断言它是原因。

### 2.2 实际的三个根因

**根因 M1：编号段落被无条件当作参考文献条目保留（已修复）**

`babeldoc_policy.paragraph_is_preserved` 中写的是 `if is_reference_heading(blob) or is_reference_entry(blob): return True`。`is_reference_entry` 的 `ENTRY_RE` 包含 `\d+\.\s+\S+` 与 `\d{1,3}\s+[A-Z]`，因此任何位置的 "2. The protocol…"、"1 We update…" 都会在送 LLM 之前被保留。这与同文件 `filter_paragraphs_for_llm` 的逻辑不一致（后者只在参考文献区内生效），也与既有测试 `test_filter_skips_glued_entries_after_heading`、`test_intext_citation_still_translatable_before_refs` 的设计不符。

影响：第 16 页统计问题第 2、3 条，第 17 页第 4 条（1135 字），第 15 页脚注 "1 We update…"。这是**不写日志**的静默跳过，所以 verify 看不见。

**根因 M2：前置信息分类把正文长句判为机构/作者行（已修复）**

- `frontmatter._AFFILIATION` 匹配 `Co., Ltd.`、`Division of`、`Food and Drug Administration` 等标记，而 `_BODY_SENTENCE` 的动词表不含 "submitted"、"discuss" 等词，于是 "On June 12, 2026, Example Biopharma Co., Ltd. … submitted this BPD Type 2b meeting request…" 被判为 AFFILIATION 并保留。这正是用户反馈的"背景"段。
- 同类问题也出现在 AUTHOR 分支：正文里出现邮箱地址即判为 `explicit author marker`，第 18–20 页的长正文段因此被保留。

**根因 M3：LLM 原样返回，BabelDOC 回退后仍是源文（已追踪，结论：不造成正文漏译）**

追踪（`scripts/qa/plan080_trace_run.py`，在 BabelDOC 处理前后记录段落 ID、送出文字、返回文字）显示，`Fallback: 3` 对应的三个段落是 **URL 脚注**（"4 http://www.fda.gov/ForIndustry/DataStandards/StudyDataStan…" 等）。模型对 URL 原样返回是合理的，不是缺陷。基线译文里逐字保留的短条目中，第 14、19、20 页的三条 URL 脚注与这三次 Fallback 一一对应。

因此：**不需要为 M3 增加"原样返回则重译"的重试**。此前"第 18 页 467 字段落可能属于 M3"的推测不成立：它在旧译文里逐字保留，是因为 M1/M2 的保留策略（见上）；修复后它被正常译出。

## 3. 装饰线（H5）

- 源文下划线中，文字宽度与线宽基本一致（中位数 0.59 是线覆盖整行时的比值，线通常只盖住行内的一个短语，属正常）。
- 译文中文行上的线，多数与译文宽度接近（中位数 0.79），但有 7 条明显过长，多为短标题（"补充意见："、"非临床"、"临床"），线仍使用英文原文的宽度。这支持 PLAN-080 的 C3 规则，但"所有下划线都过长"的说法不成立。
- 译文另有 17 条悬空线（源文 5 条）：译文重排后，原线留在原坐标，下方已没有对应文字。C3 需要同时处理"过长"和"悬空"两种情况。

## 4. 本轮改动

| 文件 | 改动 | 理由 |
| --- | --- | --- |
| `qyunslation/structure/babeldoc_policy.py` | `[n]` 形式不等标题即保留；`n.` / `n xxx` 形式只在参考文献区内保留 | M1；与既有设计一致 |
| `qyunslation/structure/frontmatter.py` | 机构标记判定要求不超过 30 词；`explicit_author` 的邮箱/corresponding 分支要求非正文句（ORCID 保持无条件） | M2 |
| `tests/structure/test_plan080_preserve_policy.py` | 新增 9 个用例，覆盖编号条目、参考文献区、[n] 引用、正文引用、附录结束、长机构句、长邮箱句、短机构行 | 防止回归 |

**生效方式**：`qyunslation/workbench/runner.py` 把仓库根目录加入子进程 `PYTHONPATH`，`_QY_033H_PRESERVE` 的 `from qyunslation.structure.babeldoc_policy import …` 在 pdf2zh 子进程中加载的就是仓库代码。因此修改在**下一次运行**时生效，不需要改 site-packages，也不需要重启 `pdf2zh.service`。若导入失败，`_QY_033H_PRESERVE` 会静默返回 `False`，即保留功能整体关闭，这一点需要在 080g 的 verify 中加检查。

## 5. 验证

| 项 | 结果 |
| --- | --- |
| `tests/structure/test_plan080_preserve_policy.py` + 参考文献、前置信息、033h、074、071e 相关用例 | 43 passed |
| `tests/structure` + `tests/pipeline` 中关键字匹配子集（reference、frontmatter、policy、033h、045、046、074、literature、author、affiliation） | 152 passed |
| 080c、080d 完成后的回归 | `tests/structure tests/pipeline tests/scripts tests/ui tests/workbench` 共 1044 passed、6 skipped、0 failed；`tests/api` 298 passed。（上一行的 3 个既有失败已由 080h 清零） |
| 全量 `tests/structure tests/pipeline`（855 项） | 846 passed，6 skipped，**3 failed**。3 个失败与本轮无关：撤回两处源码改动后仍然失败（`test_manifest_contract::test_committed_json_schema_matches_model`、`test_manifest_store::test_schema_major_mismatch_is_treated_as_miss`、`test_plan059_fidelity::test_ljae_semantic_counts_are_not_physical_image_counts`），报错均为 `MANIFEST_VERSION_UNSUPPORTED`，属于既有的 manifest schema 版本问题，需单独登记 |
| 样本重放（修复后的 `paragraph_is_preserved`，按阅读顺序） | 策略保留 33 个长段（172 中的 19%） | 修复前的完整计数没有保存，因此不做前后比较 |

修复后仍被策略保留的 33 段：抬头 "U.S. Food and Drug Administration Silver Spring, MD" 共 25 次（D1 保留范围）；发件方与地址（第 1、2 页）；FDA 与参会人名单（第 2–3 页）；JIANGSU 参会人名单（第 3 页）；第 15 页一条指南标题的项目符号（"•Guidance for Industry and Food and Drug Administration…"，按机构标记保留，属于边界情况，记入风险）。第 3、16–20 页的正文段已不在保留之列。

### 5.1 样本重译对比（单次运行）

做法：用 runner 同样的 CLI 参数（`--config-file` 为运营配置的副本且 `gui=false`、`--lang-in en --lang-out zh`、`--watermark-output-mode no_watermark`、同一份术语表、`--auto-enable-ocr-workaround`），经 `plan080_trace_run.py` 运行，仓库代码通过 `PYTHONPATH` 加载。引擎为配置里的 Ollama（`qwen3.6:35b-a3b`）。配置副本含密钥，用后已销毁。输出与追踪都在 scratchpad，报告副本在 `var/plan080/`（不入库）。

**段落级追踪（334 个段落）**

| 去向 | 数量 | 说明 |
| --- | --- | --- |
| translated | 246 | 与旧日志的 `Successful: 246` 一致 |
| skipped:preserve | 64 | 抬头、人名、职务、机构、地址、一条指南标题（D1 范围） |
| unchanged | 10 | 页码标识 "PIND 000000"、分隔线、签名 "Pat Kim" 等 |
| not_sent | 10 | 1–11 字符的短标签与项目符号，低于 `min_text_length` |
| fallback_unchanged | 3 | 三条 URL 脚注 |
| skipped:numeric | 1 | 纯数字 |

**译文前后对比（`plan080_diagnose.py`）**

| 指标 | 旧译文 | 新译文 |
| --- | --- | --- |
| 逐字保留的长段落 | 41 | 33 |
| 其中非人名职务类 | 13 | 6 |
| 非名单、≥100 字符的逐字保留段 | 8 | 1（第 15 页指南标题项目符号） |
| 全文拉丁字母数 | 9138 | 5256 |
| 全文汉字数 | 10163 | 11348 |
| 第 16 页：拉丁字母 / 汉字 | 1151 / 342 | 72 / 657 |
| 第 17 页：拉丁字母 / 汉字 | 1189 / 398 | 121 / 713 |
| 第 19 页：拉丁字母 / 汉字 | 1155 / 440 | 233 / 716 |

抽查：第 16 页新译文含"亚组"、"脱落率"、"标准差"（用户反馈的统计问题第 2、3 条）；第 3 页背景段已有中文。汉字总数增加，说明段落被译出而不是被丢弃。

**字体和下划线没有变化**（字体种类最多仍为 10；中文行下划线超限 7→8、悬空 17→18），这符合预期，因为 080c、080d 还没做。

**这次对比的限制**
- 只跑了一次，LLM 有随机性，数字不应当作精确值。
- 旧译文是生产服务当时的运行，可能带有每次运行的模型快照或自定义提示词（`model_snapshot`、`ad_prompt_text`）；这次重译只用了运营配置的默认值，也没有生产服务的环境变量（如 `PDF2ZH_LLM_BATCH_TOKENS`）。所以前后差异不全是修复带来的。能直接归因于修复的证据是段落级的：旧版用同一函数直接调用可复现"编号段和背景段被保留"，新版追踪里这些段落都进入了翻译。
- 没有渲染页面做目视核对。

### 5.2 080c 字体统一（D2：思源宋体；D3：默认关闭）

**根因**：`lang_out=zh` 时 BabelDOC 的 `FontMapper` 把多语种字体表合并（normal 里 NotoSerif 在前、思源在后；script 里 NotoSans/NotoSerif 斜体在前、霞鹜文楷在后）。结果是拉丁字符落到 NotoSerif，汉字落到思源宋体，斜体汉字落到霞鹜文楷，粗体又是另一套。

**做法**：`font_policy.install(FontMapper)` 包装 `FontMapper.map`（不改方法体）。开启（`QYUNSLATION_FONT_POLICY=unified`）后，只按粗体在 SourceHanSerifCN Regular / Bold 中选择，不再按斜体换字体；画像明确写 `primary_font_family = "sans-serif"`（书信、IND 递交资料）时用思源黑体，不静默覆盖 PLAN-008 的设定；字体族里没有该字形、目标语言不是中文、包装内部出错，都回落到原行为。生产补丁 `apply-pdf2zh-080c-fonts.py` 只在 `fontmap.py` 末尾追加一个带标记的块，已登记到补丁顺序（#37）、`pdf2zh.service` 启动链和补丁指纹表。默认 `off`，所以装上补丁不改变任何输出。

**样本重译对比（同一份源文，开启与未开启）**

| 指标 | 未开启 | 开启 |
| --- | --- | --- |
| 译文字符使用的字体 | 思源宋体 R/B、霞鹜文楷、NotoSerif R/I/B/BI | 仅思源宋体 Regular（14919 字符）与 Bold（1670 字符） |
| 每页字体种类（≥7pt）最大 / 中位数 | 10 / 6 | 5 / 4 |
| 引擎日志 `Unable to export`、缺字形告警 | 0 / 0 | 0 / 0 |

目视核对第 16 页：译文为统一的直立宋体，统计问题第 2、3 条完整；没有重叠或溢出。

**剩余的字体种类**来自**被保留的原文**（抬头 Calibri、名单与抬头 Arial、一条 Symbol），它们不经过 `FontMapper`，保持源文件字体。按 C4（080e）处理，不在 080c 范围。

**限制**：只验证了一份样本、一次运行；斜体强调在译文中丢失（思源宋体没有斜体，D2 已选定）；字体补丁已部署但开关仍关闭。生产启用需在运行翻译的环境里设置 `QYUNSLATION_FONT_POLICY=unified`（工作台 runner 子进程继承该环境变量）并重启 pdf2zh。

### 5.3 080d 装饰线随文（D3：默认关闭）

**根因**：BabelDOC 只重写文字，不重写矢量图形。源文里画在文字下面的下划线（超链接、小标题）留在原坐标，译文重排后就出现 线比文字长、线悬在空白处。

**做法**（`decoration_realign.realign_pdf(source, output)`，runner 在 CLI 成功后、记录产物前调用，开关 `QYUNSLATION_DECORATION_REALIGN=on`，默认 off；mono 与 dual 都处理，dual 的右半幅按页宽偏移）：

1. 在**源**页里确认"文字装饰线"：水平细线（高 ≤1.5pt、宽 ≥5pt）、紧贴某一文本行下沿（落在行下部 35% 或其下 3pt 内）、宽度不超过该行文字宽度 + 4pt、且两端附近没有垂直细线（排除表格线）。分隔线、页眉页脚线、框线都不满足，保持原样。
2. 译文页里同坐标的线就是它的副本。找它现在所在的译文行：找到则裁到译文文字范围内；没有但 8pt 内有横向重叠的行则挪到该行下沿；都没有则删除。裁剪或挪位后短于 16pt（不到两个汉字）或短于原线 25% 的，也删除——这是原线盖的文字（如网址）译文里已不存在的情形。
3. 删除原线用"涂抹"，只允许触碰到这条线自己：`REMOVE_IF_COVERED` 对零高度的描边线不生效（实测），必须用 `REMOVE_IF_TOUCHED`，所以擦除矩形若碰到别的矢量图形（底纹、合并路径），放弃这一条，保持原样。再按原颜色和线宽画新线。
4. 单页出错只回滚这一页的涂抹标注，不影响其他页；整个步骤出错保留原文件，不影响交付。

**样本结果（开启字体策略后的译文，处理前后）**

| 指标 | 处理前 | 处理后 |
| --- | --- | --- |
| 候选装饰线 | 69 | 69：保留 34、裁短 19、挪位 7、删除 9 |
| 中文行下划线超过文字宽度 1.3 倍 | 7（最长 2.13 倍） | 0 |
| 悬空线（找不到所属文字） | 18 | 5（与源文本来就有的 5 条分隔线一致，未被改动） |
| 因擦除会碰到别的图形而放弃 | — | 0 |
| 各页文字内容（`get_text`） | — | 与处理前逐页完全一致；图片数 21→21 |

目视核对第 15、16 页和 dual 的右半幅：链接下划线贴合链接文字，段末悬空线消失。

**已知限制**
- 没有"英文短语→中文短语"的对应关系，所以无法精确到词：小标题的下划线保持原来的左端和宽度，只是不会超出该行文字。样本第 16 页的小标题 "统计1. 在试验方案摘要第7.2节中" 下划线仍比标签文字（"统计"）稍长。
- 一条线被挪位或删除后，原本想表达的"这是超链接"的视觉提示就没有了；超链接本身（Link 注释）没有改动（样本中 0 个）。
- 只处理水平细线；删除线、波浪线、高亮块不在范围内。
- 只验证了一份样本。

### 5.4 080e 人名、职务、机构的保留（D1）

**现状评估**：样本重译里有 21 条短职务被翻译（"Clinical Reviewer, DO/OSM"、"Medical Director"、"General Manager Assistant"…），而同一份名单里 "Deputy Director, Office of New Drugs" 因含机构标记被保留，这就是"一半译一半不译"。现有分类器对不含机构标记的职务（"General Manager"、"Regulatory Lead, Acme CRO"）完全没有覆盖。

**做法**：`entity_preserve.is_job_title` 保守识别职务：整行只含首字母大写词、缩写和少数连接词，第一段以职务名词结尾或为 "职务 of/for/to …"，不含句末标点、句子动词和句首的 Please/Contact 等。接入 `paragraph_is_preserved`、`filter_paragraphs_for_llm` 与 `title_is_usable_context`（职务不作为翻译上下文）。`preserve_reason(text)` 给出固定原因 `PERSON_NAME`/`JOB_TITLE`/`ORG_NAME`，供 QA 区分"有意保留"和"漏译"。

**不做**：纯人名（两三个首字母大写词，无学位）的规则判定——它与 "Clinical Pharmacology" 这类标题无法区分，误保留标题的代价更大。这类人名仍由模型处理（样本中 "Pat Kim" 被原样返回）。

**验证**：对上次追踪里 246 个"已翻译"段落重放，新规则额外保留 25 条，全部是职务，没有误伤标题或正文。负例（标题、含职务词的句子、"Please contact the Regulatory Lead…"）有单元测试。

**门禁脚本发现的一处遗漏（已修）**：22 个词的背景句（含 "Co., Ltd."、"submitted"，但不含动词表里的词）仍被当作机构行保留；此前只靠 30 词上限不够。给"机构 vs 正文"判断加了功能词线索（this/that/the/to/by/with…：≥2 个，或超过 12 词时 ≥1 个）；"Office of the Director, Center for Drug Evaluation and Research" 这类机构行不受影响（有测试）。副作用：样本中 "Sponsor Name: … Regulatory Pathway: 351(k) of the Public Health Service Act" 一块不再被保留——这是含监管路径说明的正文，翻译才是对的。

**被保留原文的字体**：保持源文件字体（抬头、名单为 Arial/Calibri），不经过 `FontMapper`。这是有意决定：抬头和名单本来就是源文档的版式，重排它们要擦写原文，风险大于收益。它们是每页剩下那几种字体的来源。

### 5.5 080f 段落级 QA（D4：只出警告；默认关闭）

`pdf_layout.check_output_layout(source, output)`，开关 `QYUNSLATION_LAYOUT_QA=on`，接在 `inspect_pdf_pair` 对 mono 输出的检查之后；任何异常返回空，QA 不会因它失败。三个警告码已登记（`UNTRANSLATED_BODY` 已存在且是整页英文占比的 C1，所以新码叫 `UNTRANSLATED_PARAGRAPH`）：

| 码 | 判据 |
| --- | --- |
| `UNTRANSLATED_PARAGRAPH` | 译文块无汉字、≥80 字符、≥12 个词、小写开头词占比 ≥40%，且与源文同页逐字相同；排除参考文献区（状态门控，编号问题段不被排除）、`preserve_reason` 非空（人名职务机构）、网址邮箱、出现在 ≥3 页的页眉页脚 |
| `FONT_FAMILY_SPRAWL` | 某页字体种类（族 + 粗/斜体计一种，每种 ≥20 字符、≥7pt）≥7 且比源文该页多 2 种以上 |
| `DECORATION_DANGLING` | 与 `decoration_realign.plan_page` 共用判断：还有装饰线需要裁短、挪位或删除 |

**样本验证（同一份源文，五个版本）**

| 版本 | 触发的警告 |
| --- | --- |
| A 旧译文（生产当时） | `UNTRANSLATED_PARAGRAPH`×8（第 1、3、15、16×2、17、18、19 页，含背景段与统计问题 2/3/4）、`DECORATION_DANGLING` |
| B 修复保留策略后重译 | 仅 `DECORATION_DANGLING` |
| C B + 字体统一 | 仅 `DECORATION_DANGLING` |
| D C + 装饰线随文 | 无 |
| E 最新（含职务保留 + 字体统一） | 仅 `DECORATION_DANGLING` |

字体种类阈值经校准：只数族名（旧 5、新 4）区分度不够，改数"族 + 粗/斜体"（源文最大 6、旧译文最大 8 且 5 页 ≥7、字体统一后最大 4）。

**限制**：只在一份样本上校准，误报率未知，所以只做警告；`FONT_FAMILY_SPRAWL` 阈值需要更多样本；`UNTRANSLATED_PARAGRAPH` 要求同页逐字相同，页数不一致时退化为不比较源文。

### 5.6 080g 回归与沉淀

- `scripts/verify-plan-080.sh`（PASS/FAIL/BLOCKED）：文件齐全；三个新开关默认 off；保留策略的四个探针（编号问题段与背景句进入翻译、职务保留、标题不被误保留）；080 与 080h 的后端测试；相邻套件（参考文献、前置信息、QA 注册表、runner）；`QYUNSLATION_VERIFY_FULL=1` 时跑全量；设置样本与译文路径时对译文做 `UNTRANSLATED_PARAGRAPH` 检查；补丁是否已装进翻译引擎（未装则 BLOCKED，本机没有 `pdf2zh.service` 单元，无法替你确认）。
- skill：SK-Q003 增补铁律 16–19 与三行症状；SK-Q005 增补铁律 6–8 与 pitfalls 4–6（静默保留谓词、诊断顺序、`REMOVE_IF_COVERED` 的坑）；SK-Q007 修正铁律 1（Fallback 计数只覆盖已送翻译的段）。
- `error-signatures.toml` 新增 4 条（`SIG-PRESERVE-WHOLE-PARAGRAPH`、`SIG-UNTRANSLATED-PARAGRAPH`、`SIG-FONT-SPRAWL`、`SIG-DECORATION-DANGLING`）；registry 审计表加一行。

## 6. 部署记录与第二轮补缺（2026-10-20，部署之后）

**首次部署记录**：6 个提交（`f008d33`…`7100e3c`）由用户手动推送并部署。核对结果：远端与当时本地一致；`pdf2zh.service`、`qyunslation-office.service` 于 11:20 重启；安装版 `pdf2zh.service` 含 080c 的 `ExecStartPre`，引擎里有 `_QY_080C_FONT_POLICY`；近 3 小时无错误日志；三个新开关均未设置（= off），所以当时生产上生效的只有保留策略修复。生产当时运行功能分支的本地检出；后续代码已进入 `main`，二轮补缺部署见 §8。

部署后做了一轮缺口审计，发现并补了下面这些。

### 6.1 参考文献可能被翻译（我自己引入的风险，已修）

保留策略改为"编号条目只在参考文献区内保留"之后，标题写法不标准（"7. References"、"Literature Cited" 等）或没有标题的文献，引文会被送去翻译。继续用真实文献夹具验证时又发现一个更深的问题：

- `nature_comm_53384`（19 页）的译文第 17 页，参考文献被翻译成中文（"47.Bissonnette,R.等人。口服 CCR4 拮抗剂…"）。
- **根因**：BabelDOC 的 `translate()` 先跑 `process_cross_page_paragraph`、`process_cross_column_paragraph`，最后才是 `process_page`，段落顺序是版面分析的顺序，不是阅读顺序。用 `QYUNSLATION_PLAN080_TRACE_GATE=1` 记录 771 次谓词调用：保留状态只翻转两次（#741 在 "References" 打开，#751 在 "Acknowledgements" 关闭），中间只经过 9 个段落，之后的条目被翻译。Nature 的双栏版面把条目合并成"从某一条中间开头"的长段落，既没有编号开头，也落在状态机的窗口之外。
- **修复**：不再依赖顺序。`is_citation_entry`（编号开头 + 年份 + 期刊引文形状或作者缩写开头）；`is_citation_block`（段落里 ≥2 处期刊引文形状 + 年份，不要求开头）；标题识别放宽。正文里的普通引用（"Smith et al., 2020"）、单处 "doi: …"、"in 2020 that" 都不会误保留（有测试）。
- **验证**：真实文献重译，修复前 QA 标出第 16、17 页 `REFERENCE_ENTRIES_CHANGED`，修复后消失。命中的误保留只有 Wiley 的 "Downloaded from…" 水印行和期刊页眉的 DOI 行，原样保留是无害的。
- **新增 QA**：`REFERENCE_ENTRIES_CHANGED`（warning，默认关闭）：源文里的引文在译文同页不再逐字存在。

### 6.2 其他补缺

| 缺口 | 处理 |
| --- | --- |
| 保留谓词导入失败时静默关闭保留功能 | `apply-pdf2zh-fidelity-033h.py` 把引擎里的 helper 升级为"第一次失败记一条 WARNING"（行为不变）；在真实引擎文件的副本上演练通过且幂等；**重启 pdf2zh 后生效**（已在启动链里）。登记为 `033h-warn` 指纹 |
| dual 为交替页布局时装饰线会错位 | 页数不一致时整体跳过（`skipped_reason`），QA 的字体与装饰线检查同样跳过，只保留不依赖配对的检查 |
| 画像字体（书信、IND 递交资料写 sans-serif） | 策略默认一律思源宋体（D2、D5）；`QYUNSLATION_FONT_POLICY_FAMILY=profile` 才沿用画像的黑体。不改 `doc_profiles.toml` |
| 字体策略在中译英时介入 | 真实 `FontMapper` 测试发现：`lang_out=en` 时字体表里同样有思源字体，策略会把英文译文改成思源宋体。已限定为简体中文目标（zh / zh-CN / zh-Hans）；开关本就默认关闭，所以未影响生产 |
| Word / PPT 没有保留规则 | 新增 `office_preserve`，`QYUNSLATION_OFFICE_PRESERVE=on` 时，`partition_docx_segments` / `partition_pptx_segments` 对正文应用同一套规则（每份文档自己的参考文献状态），对表格单元格只应用人名/职务/机构规则；默认关闭。用真实 python-docx 文件验证（参会人表格、参考文献区） |
| 中译英方向 | 保留规则只针对英文写法；加了测试：中文原文（职务、公司名、编号句）不会被保留。中文职务与公司名照常翻译 |
| 测试覆盖 | runner 异步流程的端到端测试（伪造 CLI → 装饰线后处理 → 产物；关闭时逐字节不变；产物无法读取时仍交付）；真实 `FontMapper` 测试（用 pdf2zh 的 Python 环境，不存在则跳过）；真实 docx 测试 |
| 提交里的原文节选 | 本轮改动的文件里，公司名、参会人姓名、页码标识都换成虚构文本。**已推送的历史提交里仍有原文**；清理需要重写历史并强制推送，由用户决定 |
| 灰度上线说明 | `docs/runbooks/plan-080-rollout.md`：开关放哪、开启顺序、判据、回滚 |

### 6.3 多样本标定（4 份文档，真实重译）

| 文档 | 方向、页数 | 字体种类/页（源文 → 关闭 → 开启，最大值） | 新 QA |
| --- | --- | --- | --- |
| 监管信函（FDA 会议纪要） | 英→中，28 | 6 → 8 → 4（旧译文 → 字体统一） | 旧译文：`UNTRANSLATED_PARAGRAPH`×8；修复后无 |
| 期刊文章 `ljae439` | 英→中，10 | 3 → 5 → 3 | 无 |
| 文献 `nature_comm_53384` | 英→中，19 | 7 → 6 → 5 | 修复前 `REFERENCE_ENTRIES_CHANGED`（第 16、17 页）；修复后仅 `DECORATION_DANGLING`×3 |
| 中文登记表 | 中→英，5 | 2 → 4 → （策略不介入） | 无 |

结论：`UNTRANSLATED_PARAGRAPH` 在 4 份文档的修复后输出里 0 误报（样本小）；`FONT_FAMILY_SPRAWL` 阈值（≥7 且比源文多 2）偏保守，只会标出旧译文那种极端情形，3 份新文档的"关闭"输出都没有触发，不是漏报：它们的字体种类（5–6）确实没有极端到那个程度；`DECORATION_DANGLING` 能在文献上检出悬空线。

## 7. 仍然开放

1. **在生产上用真实作业验证**：重新部署后还没有用真实作业跑过；按 runbook 用 `QYUNSLATION_PLAN080_SAMPLE`/`QYUNSLATION_PLAN080_OUTPUT` 运行 `verify-plan-080.sh`。
2. **按 runbook 灰度开启四个开关**：由用户决定范围与时间；本次部署没有修改服务环境配置。
3. **已推送历史里的原文节选**：见 6.2。
4. **已知限制**：小标题下划线无法精确到词；被保留的原文保持源字体；斜体强调丢失；纯人名不做规则判定；装饰线只处理水平细线；非标准引文格式（无卷页、DOI、et al.）可能仍被翻译，开启 QA 后会被 `REFERENCE_ENTRIES_CHANGED` 报出。

## 8. 生产重新部署记录

- **时间**：2026-10-20 15:53 CST。维护脚本 `scripts/deploy-translate-stack.sh` 部署并重启了用户级 `pdf2zh.service` 与 `qyunslation-office.service`。
- **代码版本**：脚本运行时工作树 HEAD 为 `891da2e5`；该提交只增加 PLAN-081 计划文档，生产行为代码与已在 `origin/main` 的 `b532a1d0` 一致。未推送 PLAN-081 文档分支。
- **重启前门禁**：Alembic 迁移版本与代码 head 对齐，前端构建新鲜；7 个本地运行状态文件均为终态，未发现活动翻译 CLI 进程。
- **重启后核验**：两个 systemd 用户服务均为 `active`；sidecar 健康检查通过，本地和远端代码指纹均为 `7542777de0fd`；API 路由门禁通过；GUI `127.0.0.1:7860/` 返回 HTTP 200。
- **范围**：未应用数据库迁移、未运行真实翻译作业，也未启用 `QYUNSLATION_LAYOUT_QA`、`QYUNSLATION_DECORATION_REALIGN`、`QYUNSLATION_FONT_POLICY` 或 `QYUNSLATION_OFFICE_PRESERVE`。本次部署未重跑测试套件；既有测试结果见本 WT 前文。
