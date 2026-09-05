---
name: scanned-doc-layout-fidelity
description: >-
  扫描件 OCR 译文版式保真：去纵向重叠盒、角色感知聚合、落款中文行款、信头 logo/印章
  译后回插、企业专名不乱译、会议信息表两列、章节标题字号、跨页上下文。触发：扫描件、
  OCR 版式、中英叠字、碎片段落、微段落、落款行款、信头 logo、专名不翻译、会议类型、
  Meeting Type、会议初步意见、引言、背景、跨页、表格错乱、hpd_ocr。
---

# 扫描件版式保真（SK-Q001）

qyunslation 自治 Skill。不改泰州 HPD。裁图过滤可参考 Hermes `lit-figures.py`，但**只做译文回插**，不入库 Vault。

## 铁律

1. **OCR 盒不得纵向重叠**——重叠区会被版式模型切成微段落，字号塌到 `目标 × 0.2`。用 `_deoverlap_boxes`；debug 看 `clamped`。
2. **角色决定是否聚合**——`MERGE_ROLES={body,header,footer}`；落款/地址逐行。
3. **图只能译后回插**——`ocr_workaround` 丢栅格 + 铺白底；`graphic_regions` → `graphic_reinsert`。
4. **专名先进表**——`glossaries/proper-nouns.csv`；未登记保持英文 identity，禁止 LLM 猜中文名。
5. **判据落 verify**——`scripts/verify-plan-010.sh`；未断言的口径不算生效。
6. **会议信息表必须两列对齐、统一字号**——`split_kv_rows` + `pack_kv_table`；`kv` 固定 10pt。申办方与监管路径必须分行。
7. **章节标题同级、加粗、大于正文**——`会议初步意见` / `引言` / `背景` 都是 `section` 14pt **粗体**。引言正文与背景正文同一 Regular 12pt、同一行宽/行距；禁止引言微字或截断。
8. **原文未断则译文不断**——页底「该 / 机构发送了会议请求批准函」在原文是同一句（下页才写完），必须接成一句正文，不得另起缩字行。
9. **全文翻译必须带跨页上下文**——生产译整本，不拆单页当终稿。页首/页尾半句按正文续译，不当标题/题注。提示见 `letter_translate_prompt.py`；单页夹具用 `QYUNSLATION_TRANSLATE_CONTEXT` 塞上页末段+下页首段。
10. **已验收页是视觉 SSOT**——会议初步意见页以 `deliverables/plan-010-fidelity/letter.page2.mono.png` 为准；问答续页以 `letter.page3.mono.png` 为准。字号/粗体/表/跨页句见同目录 `reference.md`。后续改排版先对金样，禁止回退到 BabelDOC 串栏或引言微字。
11. **模型只出译文，重绘才出页**——切回 `qwen3.6:35b-a3b` 算译文质量，不算版式。每页必须 OCR 英文全文 → 模型/金句 → 空白页 `kv_reinsert`。生产 GUI（正式书信 + HPD debug）走 `letter_pipeline`，禁止把 BabelDOC PDF 当终稿。
12. **问答页按内容量分档，不堆在天头**——默认正文 12pt / 行距 1.50 / 段距 12pt（章节 14pt，保持 +2pt）。疏页升正文 **13pt**、章节 **15pt**，行距 1.58–1.88、段距 14–24pt，目标占版心（y≈118–740）的 80–88%。≤8 行只略放大、不拉满；超长锁 12pt、行距 1.38，禁止小于 12pt、禁止丢段。详表见 `reference.md`「版心与行距」。

## 已验收口径（会议初步意见页）

| 块 | 字号 | 字体 |
| --- | --- | --- |
| 会议初步意见 / 引言 / 背景 | 14pt | Bold |
| 会议表标签\|值 | 10pt | Regular |
| 引言正文、背景下文 | 12pt Regular，同宽同行距 | |
| 参考编号 | 8.5pt | Regular |

申办方与监管路径分行；`GS301` 与其它表值同号；原文未断句（含跨页半句）译完接成一句。详表见 `reference.md`。

## 施工顺序（letter）

```
行级 blocks → clean_text → split_kv_rows → split_named_sections → pack_kv_table
→ clamp_before_section_heads → tag_blocks → 图形区丢 suppress 行
→ MERGE_ROLES 聚合（kv/落款/地址不聚合）→ _deoverlap_boxes（跳过 kv）→ _expand_boxes
→ insert_textbox（kv 10pt / section 14pt）→ BabelDOC(+glossaries+跨页提示)
→ graphic_reinsert → kv_reinsert（表 + 章节标题重绘）
```

## 排障

| 现象 | 看 |
| --- | --- |
| 2.4–6pt 碎字 | `*.hpd-debug.json` 重叠/`clamped`；BabelDOC scale |
| 落款挤成一块 | `role`/`MERGE_ROLES`；`signature_align` |
| logo 没了 | `*.graphics.json`；是否走了 reinsert |
| GenScend→金斯瑞 | `proper-nouns.csv` / `--glossaries` |
| 会议表错乱 / `Se` / 编号断开 | `split_kv_rows` + `pack_kv_table`；debug `role=kv` 且字号=10 |
| 申办方与监管路径同一行 | `pack_kv_table` 分行 + `kv_reinsert` 按盒重绘 |
| 产品名称字号偏小 | kv 禁止 `_fit_fontsize` 降到 6pt |
| 引言后微字 / 引言比背景小 | `section` 14pt + 引言正文走 `body` 12pt；`kv_reinsert` |
| 会议初步意见太小 | 角色必须是 `section`，不是 `header` |
| 页底半句缩成脚注 | `tag_paragraph_text` 勿单靠 `y>0.82` 判 footer |
| 跨页指代/半句断裂 | 译整本；`letter_translate_prompt.py` |
| 中英叠字 | 是否误恢复 `base_operations`（禁止） |

## 关键脚本

- `scripts/hpd_ocr.py` / `letter_layout.py` / `doc_profile.py`
- `scripts/graphic_regions.py` / `graphic_reinsert.py`
- `scripts/proper_nouns.py` / `glossaries/proper-nouns.csv`
- `scripts/kv_reinsert.py` / `letter_translate_prompt.py`
- `scripts/verify-plan-010.sh`

踩坑见 `pitfalls.md`；已验收页详表见 `reference.md`。
