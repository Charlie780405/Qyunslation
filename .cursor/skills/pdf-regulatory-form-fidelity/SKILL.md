---
name: pdf-regulatory-form-fidelity
description: >-
  临床监管表单 PDF 完整翻译与表格版式保真：无题注矢量表格、中英混排短标签、单元格回写、
  微字/溢出硬失败、原文清除、固定字段直替、断词约束、受控实体、告警交付、
  源抽取行分桶、格级残留隔离、表级字号归一。
  触发：监管表单、临床试验登记、无题注表格、单元格漏译、微字、中文残留、
  FONT_BELOW_TARGET、SOURCE_RESIDUE、SHORT_LABEL、WORD_SPLIT、CELL_MERGE、
  SPAN_ORDER_DRIFT、FONT_MIX、RESIDUE_RATE、PLAN-041、PLAN-042、PLAN-043、PLAN-044、REGULATORY、
  整段没翻译、编号问题漏译、字体不统一、下划线过长、职务没翻译、PLAN-080。
---

# 临床监管表单 PDF 保真（SK-Q003）

## 铁律

1. **无题注也要进表格链**——Word 导出表单常无 `Table N`；走 captionless 网格，禁止运行时 `page.find_tables()`。
2. **有汉字就译**——中英混排/短标签不得因目标语种占比被跳过。
3. **短标签直替（042b/043a）**——登记表固定字段与 1–4 字值格走 `glossaries/regulatory-form-fields.csv`（layer=`form`）译前精确直替；**必须** `post_translate_paragraph` 写回 composition。禁止只改 `paragraph.unicode`；写回失败**不得** skip LLM。**不要**裸降 `min_text_length`。
4. **单元格政策**——空格与纯数值 `PRESERVE`；注册号/方案号/电话/邮箱/日期占位保护，丢失即 `TABLE_TOKEN_DRIFT`。
5. **真清除原文**——redaction 后再绘译文；单元格 bbox 可小幅膨胀覆盖多行源 span（042d）。
6. **字号下限只告警**——正文 `max(7pt, 源×70%)`，脚注 5.5pt。`FONT_BELOW_TARGET` 属 `TABLE_QC_SOFT`（043c），**不**阻断 `.tbltr.pdf` 写出；**不**进图片 `HARD_FAIL`。REGULATORY 另用表级阶梯 `TABLE_ROLE_SIZE`（044d：header 8 / cell 7 / footnote 6）。
7. **表格链部分交付（043c/044c）**——任一表写回成功即可产出 `.tbltr.pdf`；`terminal_success=false` 当有表硬失败。**REGULATORY**：`SOURCE_RESIDUE`/`MISSING_TARGET` 为**格级降级**（保留中文并统一字体重绘）；仅残留率 >30%（`RESIDUE_RATE`）或 `CELL_MERGE` 等仍表级硬失败。**文献 RESEARCH/REVIEW** 同样 isolate（否则 OVERFLOW 在 paint 前整表回退，字号归一不落笔）；英源中文译文不算 `SOURCE_RESIDUE`。
8. **告警交付（042f）**——表格链失败时 GUI 进度须含「N 个表格未保真」+ 逐表 reason；禁止静默伪成功。
9. **受控实体（042e）**——申办方/医院/院校/人名命中 org/form 词表或保留原文；禁止模型自由猜译。章节序号与 II 期罗马数字走确定性映射。
10. **断词（042c/044d）**——regulatory 画像启用英文整词换行，禁止词内断裂；`paint_cell` inset 横向 ≥1.5pt、纵向 ≥1.0pt，避免压格线。
11. **实样不入库**——041→`QYUNSLATION_PLAN041_SAMPLE`；042/043→对应 env；044→`QYUNSLATION_PLAN044_SAMPLE` / `QYUNSLATION_PLAN044_EN_OUTPUT`。
12. **判据**——`verify-plan-041.sh` … `verify-plan-044.sh`。
13. **路径分工（043 诊断）**——文字层长段落走 BabelDOC 通常 OK；**表单短标签**优先表格链；表格链失败时 043a 段落直替为回退保险。
14. **源抽取重建（044a）**——单元格 span 必须行分桶（基线容差）+ CJK/标点零空格连接 + 软换行合并。禁止裸 `sorted(y0)` + `" ".join`（会导致 `序 号`、`、受试者信息 3`、`2 周一 次`）。
15. **批内完整性（044b）**——LLM 缺索引须单条补译；**禁止**把源文静默写入缓存当译文。中文仍缺则回填源文供重绘；非中文空串走 `MISSING_TARGET`。

16. **整段漏译先查保留谓词（PLAN-080）**——译文里与源文同页逐字相同的长段落，必须有保留原因（`PERSON_NAME`、`JOB_TITLE`、`ORG_NAME`、网址、参考文献区、重复页眉页脚），否则就是漏译：QA 码 `UNTRANSLATED_PARAGRAPH`。详见 SK-Q005 铁律 6–7。
17. **人名、职务、机构原文保留（D1，PLAN-080e）**——职务由 `structure/entity_preserve.py` 识别（整行只含首字母大写词、缩写与少数连接词，第一段以职务名词结尾或 "职务 of/for/to …"，不含句末标点和句子动词）。**不做**"两三个首字母大写词就是人名"的判定：它与 "Clinical Pharmacology" 之类标题无法区分，误保留标题的代价更大。带学位的人名走 frontmatter 的作者判定。
18. **字体统一（D2，PLAN-080c）**——`lang_out=zh` 时 BabelDOC 合并多语种字体表，斜体汉字走霞鹜文楷、拉丁走 NotoSerif。开启 `QYUNSLATION_FONT_POLICY=unified` 后译文只用思源宋体 Regular/Bold（画像写 sans-serif 时用思源黑体）。被保留的原文不经 `FontMapper`，保持源文件字体；这是有意的，不是漏统一。
19. **装饰线随文（PLAN-080d）**——BabelDOC 不重写矢量图形。`structure/decoration_realign.py` 只处理源页里确认是文字装饰的线（贴行下沿、不宽于文字、非表格线），按译文文字范围裁短/挪位/删除；无法精确到词，小标题线只保证不超出所在行。擦除只能碰到线自身。
20. **参考文献按形状保留（PLAN-080）**——期刊引文（卷:页、DOI、et al.、年份）单条看开头、合并成长段落看密度，不依赖"References"标题和段落顺序；标题写法放宽到 "7. References"、"Literature Cited"、"Works Cited" 等。QA 码 `REFERENCE_ENTRIES_CHANGED` 检查源文引文在译文同页是否逐字保留。
21. **Word / PPT（PLAN-080）**——`partition_docx_segments` / `partition_pptx_segments` 在 `QYUNSLATION_OFFICE_PRESERVE=on` 时对正文和表格单元格应用同一套人名、职务、机构、引文规则；每份文档用自己的 `ReferencePreserveGate`，不共享 PDF 路径的全局状态。
22. **字体策略只对简体中文目标生效**——`lang_out` 为 en、zh-TW 等时不介入（字体表里虽有思源字体，但不是统一对象）。字体族默认思源宋体（D2），`QYUNSLATION_FONT_POLICY_FAMILY=profile` 才沿用画像的黑体。

## 错误台账

见 `docs/plans/PLAN-042-regulatory-translation-quality/error-taxonomy.md`（含 H 族源抽取与 044 扩充）。

## 044 修复配方（复用）

| 症状 | 先查 | 修法 |
| --- | --- | --- |
| 孤字/乱序短标签 | 源 `source_text` 是否含 `序 号` 类 | 044a `compose_cell_text` |
| 整表失败但多数格已译 | execution `SOURCE_RESIDUE` | 044c 格级隔离；确认画像 REGULATORY |
| 同页三套字体 | 是否几乎无 `.tbltr` 实绘 | 先抬交付率，再 044d 归一 |
| 微字/压线 | `fit_group` tier + inset | `normalize_table_sizes` + role-aware inset |
| 批内大量「译文=原文」 | `_llm_translator` 缓存 | 044b；清 `/tmp/plan033m-table-zh-cache.json` 后重译 |
| 文献表字号 9 种/漏译 | 有无 `.tbltr` / 门禁 reason | 047e `pdf_table_normalize`；literature OVERFLOW 软化 |
| 期刊三线表串格/列并 | `grid_source` / HPD | **SK-Q009** PLAN-048 HPD 网格；禁止 geometry_center 落笔 |
| 编号问题/背景段整段英文，日志无 Fallback | 追踪报告该段 fate | SK-Q005 铁律 6；收紧保留谓词 | `UNTRANSLATED_PARAGRAPH` 消失 |
| 同页宋体、楷体、衬线斜体混用 | `plan080_diagnose.py` 的 `font_family_max_per_page` | `QYUNSLATION_FONT_POLICY=unified` | 译文字符仅思源宋体 R/B |
| 下划线比文字长或悬空 | `decoration_realign.plan_page` | `QYUNSLATION_DECORATION_REALIGN=on` | `DECORATION_DANGLING` 消失 |
