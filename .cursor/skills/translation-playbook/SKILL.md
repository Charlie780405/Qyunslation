---
name: translation-playbook
description: >-
  qyunslation 翻译总入口（任何翻译/重译/译文质量任务先读它）：译前预检、译中取证、译后验收、
  症状路由到分域 skill、QA 警告什么该报什么不该报、近期计划质量改进汇总。
  触发：翻译、重译、重新翻译、译文、文献翻译、PDF 翻译、表格译文、译文有错、译文缺漏、
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
| 漏翻译 / 整段英文 | `UNTRANSLATED_PARAGRAPH`、Fallback 计数 | SK-Q007 |
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
| `LITERAL_MISSING_EMAIL/IND`、剂量/频次 | 保持 | 事实性错误 |
| `QA_INSPECTION_SUMMARY` | 保留（INFO，审计用） | 不要求处理 |

新增/调整 QA 规则时：写明误报形态 → 加「真的丢了仍报」与「噪声不报」两个测试 → 需要时加环境开关而不是删规则。

## 表格译文规则（速记，细则见 SK-Q009）

- 单元格是否送翻译看**内容**：纯数值/单位/占位才保留；`3 (Moderate)`、`12 (SD 3.4)` 含文字必须翻译，`46.1 (18.3)` 保留。
- 数字比对先归一：细空格、全角括号、上标数字（`m²`≡`m2`）视为同一数字；某格真漂移只让**该格**保留原文，不拖垮整表。
- 单位角标：文本层把 `kg/m²` 压平为 `kg/m2`，译后对 `[kcmμ]?m` 后的 `2/3` 还原为 `² ³`；不碰 `IL-2`、`M2`、`EASI-75`。负指数 `mL⁻¹` 字体无字形，保持 `mL-1`。
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
