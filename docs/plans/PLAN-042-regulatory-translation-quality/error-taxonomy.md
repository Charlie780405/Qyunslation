# PLAN-042 错误分类台账

> 证据：CTR20231233 登记表 5 页中英对照截图（不入库）。
> 根因层：`babel` = BabelDOC 段落路径；`tbl` = 041 表格链；`gui` = 交付层；`gloss` = 术语表。

| ID | 族 | 现象 | 根因层 | 子计划 | 门禁码 |
| --- | --- | --- | --- | --- | --- |
| A1 | 漏译 | 1–4 字值格整格未译 | babel `min_text_length=5` | 042b | `SHORT_LABEL_OMISSION` |
| A2 | 漏译 | 长列表条目部分未译 | babel + tbl fallback | 042b/d | `LIST_ITEM_OMISSION` |
| A3 | 漏译 | 单元格前译后残（中文尾巴） | babel redact 不全 | 042d/e | `SOURCE_RESIDUE` |
| A4 | 漏译 | 表头/列标题未译 | babel 短标签 | 042b | `HEADER_OMISSION` |
| B1 | 版式 | 字号塌陷至 3–5pt | babel typesetting | 042f | `FONT_BELOW_TARGET` |
| B2 | 版式 | 词内断裂插空格（sc ore） | babel typesetting | 042c | `WORD_SPLIT` |
| B3 | 版式 | 断词损坏拼写（Mono-Long） | babel typesetting | 042c | `WORD_CORRUPT` |
| B4 | 版式 | 越界压入相邻格 | babel + tbl | 042d/f | `OVERFLOW` |
| B5 | 版式 | 译文叠印未清除源文 | redact 不全 | 042d | `SOURCE_RESIDUE` |
| B6 | 版式 | 标签译文整体下移一行 | paragraph 归属 | 042d | `LABEL_VALUE_SHIFT` |
| C1 | 结构 | 跨单元格合并（人名并入机构） | paragraph_finder | 042d | `CELL_MERGE` |
| C2 | 结构 | 键值对塌陷同格 | paragraph_finder | 042d | `KEY_VALUE_COLLAPSE` |
| C3 | 结构 | 地址成分语序错乱 | babel 切分 | 042d/e | `ADDRESS_ORDER` |
| D1 | 术语 | 申办方名错译 | gloss 缺失 | 042e | `ENTITY_MISMAP` |
| D2 | 术语 | 医院院校名错译 | gloss 缺失 | 042e | `ENTITY_MISMAP` |
| D3 | 术语 | 人名音译错误 | gloss 缺失 | 042e | `PERSON_MISMAP` |
| D4 | 术语 | 幻觉造词 | 模型自由生成 | 042e | `HALLUCINATION` |
| D5 | 术语 | 登记表固定字段译名不受控 | gloss 缺失 | 042b/e | `FIELD_LABEL_DRIFT` |
| E1 | 编号 | 章节序号错误且重号 | 无确定性映射 | 042e | `SECTION_NUM_DRIFT` |
| E2 | 编号 | 罗马数字被读成阿拉伯（II→11） | 源抽取 | 042a/e | `ROMAN_DIGIT_DRIFT` |
| E3 | 编号 | 量词误译（日→points） | gloss | 042e | `MEASURE_MISMAP` |
| E4 | 编号 | 计量词不一致（分→points/score） | gloss | 042e | `MEASURE_INCONSISTENT` |
| F1 | 语义 | 关键限定语丢失 | babel 截断 | 042e/f | `SEMANTIC_LOSS` |
| F2 | 语义 | 重复赘译 | 模型 | 042f | `REDUNDANT_TRANSLATION` |
| F3 | 语义 | 句段孤立漂移 | typesetting | 042c/d | `SENTENCE_DRIFT` |
| G1 | 交付 | 表格链硬失败静默回退 | gui | 042f | `SILENT_TABLE_FALLBACK` |
