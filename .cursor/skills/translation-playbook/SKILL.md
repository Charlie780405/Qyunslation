---
name: translation-playbook
description: >-
  qyunslation 翻译总入口（任何翻译/重译/译文质量任务先读它）：译前预检、译中取证、译后验收、
  症状路由到分域 skill、QA 警告什么该报什么不该报、近期计划质量改进汇总。
  触发：翻译、重译、重新翻译、参考文献警告、下角标、表头重叠、译文、文献翻译、PDF 翻译、表格译文、译文有错、译文缺漏、
  漏翻译、没翻译出来、角标、上标、下标、m2、kg/m2、中度、重度、括号里的英文、警告没有意义、
  QA 警告、误报、批准的术语译名未出现、网址丢失、进度条不动、没有进度条、浏览器里中文不显示、
  字体没内嵌、改了没效果、验收、PLAN-082、PLAN-083、PLAN-083b、PLAN-083c、SK-Q012。
---

# 翻译总入口（SK-Q012）

这是**入口与清单**，不重复分域细节。症状→分域 skill 见下表；近期计划的质量改进见 [plan-quality-digest.md](plan-quality-digest.md)。

## 铁律（每次翻译任务都适用）

1. **先取证再改**：失败看 `runner.log`、`state.json`、manifest `output_evidence`、QA 条目 `evidence_json`，不凭截图猜。
2. **用真实路径验收**：假译员/离线脚本通过不等于线上通过。PLAN-083b 离线全绿、线上仍整表失败，因为真实 LLM 把 `n = 30` 的细空格改了。验收要用**真实译文缓存或真 LLM**，并在**浏览器查看器**里看（pymupdf 渲染会兜底缺字体，浏览器不会）。
3. **规则不是针对一份文件**：一个现象 → 找出同类 → 改规则 → 加回归测试；禁止为让某份 PDF 好看写特例。
4. **失败要无声无害**：任何新路径出错，整块交回 BabelDOC 原样，不叠加归一/居中/补翻等第二次改动；绝不留半成品。
5. **QA 只报有行动价值的**（见下节）。新增检查先影子/默认关，量过误报率再开。
6. **每次交付沉淀**：跑 `scripts/skill-pitfall-capture.py`；新坑进 `pitfalls-inbox.md`，经 `--promote` 进正式 skill（SK-Q008）。
7. **部署只走** `bash scripts/deploy-translate-stack.sh`（含 `daemon-reload`）；裸 restart 被 hook 拦截（SK-Q004）。

## 译前预检

| 检查 | 命令/位置 | 不通过怎么办 |
| --- | --- | --- |
| 进程/补丁一致 | `deploy-translate-stack.sh` 双侧指纹 | 先部署，再谈效果（SK-Q004） |
| 补丁是否被覆盖 | `apply-pdf2zh-*.py` 标记 | SK-Q005 |
| 文档画像 | manifest `content_profile`（RESEARCH/REVIEW=文献，REGULATORY=监管） | 画像决定表格/字号/QA 分支 |
| 资料等级与模型 | 机密不得走外部模型（PLAN-073c） | 改用内部模型档 |
| 术语库版本 | `glossaries/term-candidate-rules.toml` `version` | SK-Q011 |
| 字体 | `~/.fonts/NotoSansSC-Regular.otf`；`fonttools` 已装 | 表内中文需内嵌子集（见下） |

## 症状路由

| 症状（用户原话） | 先看 | Skill |
| --- | --- | --- |
| 表格串格 / 列没对齐 / 字号不一 / 行丢了 | 表是否走重建，`output_evidence.reason_code` | SK-Q009 + [literature-rebuild.md](../table-translation-fidelity/literature-rebuild.md) |
| 表格里中文没了只剩英文 | 落笔字体是否内嵌（`page.get_fonts()` 看 `n/a`） | SK-Q009 |
| 中度/重度、括号里的字没翻译 | `is_preserve_cell` 是否把带字括号当数值 | SK-Q009 |
| 角标 m2 / 上标丢了 | 文本层压平上标；单位指数是否还原 | SK-Q007 |
| 表里 Tmax / AUC0-τ / t1/2z 下标没了；`mga` 译成 `mg/kg` | `script_pairs`、`set_script_pairs` | SK-Q009 R10 |
| 表头文字叠在一起 / 深色表头变白底 / `SAD phase` 被拆开 | `n_header_rows`、`snapshot_fills` | SK-Q009 R11 |
| 脚注被拆进各列 | `table_bottom` | SK-Q009 R12 |
| 破折号显示 `?` | `_helv_has` | SK-Q009 R13 |
| 漏翻译 / 整段英文 | `UNTRANSLATED_PARAGRAPH`、Fallback 计数 | SK-Q007 |
| 乱码阻断（`TEXT_ENCODING_ARTIFACT`）但译文肉眼看不到乱码 | 是文本层问题不是画面：`QYUNSLATION_ENCODING_INHERITANCE`（默认 `auto`）；符号字体 ToUnicode 缺 | SK-Q007 坑 4–6 |
| `±` 变成 `-` / `≥` 丢了 / `©` 乱码 | 源 PDF 的 `AdvPSSymbol/AdvPSSym` 子集字体 ToUnicode 错；`QYUNSLATION_FIX_SYMBOL_CMAP` | SK-Q007 坑 5 |
| Introduction 首字母大写 A 与正文叠字 / 中文首字不突出 | 首字下沉被当公式；`QYUNSLATION_FIX_DROPCAP`、`QYUNSLATION_DROPCAP_ZH_SCALE` | SK-Q006 坑 5 |
| 表头少列 / 表题「表 1.」消失 / 深色标签条空白 | 表头 rc<0 不落笔；redact 误伤表题；深色条标签 | SK-Q009 R14–R16 |
| 横向（旋转）表格完全没翻译 | 页面文字方向是竖的：`source/rotations.json`、`QYUNSLATION_ROTATED_PAGES` | SK-Q009 R17 |
| 表里汉字比数字淡 / 第一列字体和数字不一致 | `.env` 的 `QYUNSLATION_FONT` 是可变字体（默认 Thin）：看落笔字体名是否 `Thin` | SK-Q009 R18 |
| 表格个别格仍是英文 / 译文串到邻格 | 批量译文错位 + 数字守恒回退源文；`table_translate._retry_single_cell` | SK-Q009 R19 |
| 横向表重建失败 `collapsed_rows` / 表题条被叠字 | 页边竖排文字混进表框；条上标签含 U+0003；表框左缘被污染 | SK-Q009 R20–R21 |
| 乱码阻断但只是项目符号 / 页眉分隔符 | `symbol_glyph_evidence`：独占词位的 C0/U+FFFD 降为 `TEXT_LAYER_SYMBOL_GLYPH` 警告 | SK-Q007 坑 7 |
| 图内文字 | 图片链 | SK-Q002 |
| 监管表单 | HPD 网格 | SK-Q003 |
| 段落丢 / 摘要碎片 / 顺序乱 | never-drop、全局状态机 | SK-Q005、SK-Q006 |
| 改了没效果 / 依然如故 | 代码在哪个进程？指纹？ | SK-Q004 |
| 进度条不动 / 停在 99% | BabelDOC 之后的后处理是否汇报 | 本 skill「进度」 |
| 术语候选异常 / 规则进化 | 裁定通道 | SK-Q011 |
| 新错误日志 | 签名表 | SK-Q008 |

## QA 警告：什么该报、什么不该报

判据：**这条警告会不会让审阅人去改点什么？** 不会就是噪声。

| 警告 | 处理 | 原因 |
| --- | --- | --- |
| `LITERAL_MISSING_URL` | 比对前必须去零宽字符 `U+200B/200C/200D/2060/FEFF/00AD`；丢弃被换行截断的前缀碎片 | PDF 常在网址点、斜杠后塞零宽空格，肉眼相同、字符串不等；一条网址折成多行会产生 `https://`、`https://doi` 之类碎片 |
| `TERM_TARGET_MISSING`（低风险词） | **默认不报**；`QYUNSLATION_QA_LOW_RISK_TERM_WARN=on` 才恢复 | `discontinuation→停药`、`pharmacokinetics→药代动力学` 常有等价译法，逐词报没有行动价值 |
| `TERM_HIGH_RISK_CONFLICT` / 禁用译法 | **必须报**，阻断 | 药名、适应症、终点译错后果严重 |
| 参考文献区里的网址/DOI/英文行 | **不报、不阻断**：参考文献整区保持原文不翻译，QA 先 `strip_reference_section` 再查 `LITERAL_MISSING_*` 与 `LATIN_RESIDUE` | 它们本来就该是英文原样；只认独立的 `References/参考文献` 标题行，到 `Appendix/致谢` 为止；正文里的网址仍照查 |
| `LITERAL_MISSING_EMAIL/IND`、剂量/频次 | 保持 | 事实性错误 |
| `QA_INSPECTION_SUMMARY` 及所有 INFO 提示 | 保留落库（审计、自动 QA 幂等依赖它），但**不计入「未处理」、不占待处理数、不当阻塞**；只在「全部」里可查，详情写「无需处理」 | 提示是检查记录，不是待办（`labels.js` `isOpenItem`/`isInfoItem`） |

新增 INFO 级规则时：只在 `registry.py` 登记为 INFO，不要给它配处置动作；前端按 `severity==='info'` 自动排除出待办。

新增/调整 QA 规则时：写明误报形态 → 加「真的丢了仍报」与「噪声不报」两个测试 → 需要时加环境开关而不是删规则。

## 表格译文规则（速记，细则见 SK-Q009）

- 单元格是否送翻译看**内容**：纯数值/单位/占位才保留；`3 (Moderate)`、`12 (SD 3.4)` 含文字必须翻译，`46.1 (18.3)` 保留。
- 数字比对先归一：细空格、全角括号、上标数字（`m²`≡`m2`）视为同一数字；某格真漂移只让**该格**保留原文，不拖垮整表。
- 单位角标：文本层把 `kg/m²` 压平为 `kg/m2`，译后对 `[kcmμ]?m` 后的 `2/3` 还原为 `² ³`；不碰 `IL-2`、`M2`、`EASI-75`。负指数 `mL⁻¹` 字体无字形，保持 `mL-1`。
- 表头/格内标点紧凑化（仅文献重建）：半角括号、`(n=30)`；组名与 `(n=…)` 之间留一个空格作换行点，窄列在此换行，不在括号内折断，也不要删这个空格（删了整表会被迫缩字）。
- 角标：`Tmax`、`AUC0-τ`、`t1/2z`、`Vz/F` 按下标绘制（原文真实小号 span ∪ 内置 PK 写法），`150 mga` 的脚注上标翻译前拿掉、译后接回；只在文献重建期间开启。
- 表头：分组行（`SAD phase`）自成一行，列表头各行合并成一格；深色表头保留底色、用白字；脚注不进表、不擦。
- 整表一个字号，取原文 span 真实字号（不是词框高度），放不下整表一起降档，数值格不折行。
- 中文必须**内嵌子集字体**（`prepare_embedded_font`），不得依赖 `china-ss`；全字库会让提取文字出现兼容字（「不」→U+F967）。

## 进度

BabelDOC 日志进度压缩到 0–89%；90–99% 给后处理（装饰线、字体映射、表格 mono/dual 逐张）。**只增不减**，失败吞掉。新增任何 CLI 之后的耗时步骤，都要接 `Pdf2zhRunner._report_postprocess`。

## 译后验收清单

1. `output_evidence`：每张表 `literature_rebuild_painted` 或带原因的 `left_babeldoc`。
2. 浏览器查看器看 mono + dual：列对齐、字号统一、中文可见、角标、`(Moderate)` 已译。
3. QA 面板：只剩有行动价值的条目。
4. 进度条全程前进。
5. 跑 `scripts/skill-pitfall-capture.py`；有新坑走 promote。
