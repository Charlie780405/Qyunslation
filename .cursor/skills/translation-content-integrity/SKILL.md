---
name: translation-content-integrity
description: >-
  译文内容完整性：Fallback 段落、拉丁残留、药名漂移、剂量口径 Q2W/Q4W。
  触发：漏翻译、译文里有英文、Fallback to simple translation、药名不对、
  剂量口径、Q2W、Q4W、每周两次、特罗金、发现gs、拉丁残留、术语不一致、PLAN-047d、
  角标、上标、m2、kg/m2、中度、重度、括号里的英文没翻译、网址丢失误报、零宽空格、术语译名未出现误报、PLAN-083c。
---

# 译文内容完整性（SK-Q007）

## 铁律

1. **日志 `Successful/Fallback` 计数必须进 verify**——Fallback 段落单独重译并校验残留拉丁串。
   **但它只覆盖已送进 LLM 的段落**：被保留谓词在送翻译之前跳过的段落（编号问题、被误判为机构/作者的正文句）不在计数里，日志也没有任何痕迹（PLAN-080a）。另需用 `QYUNSLATION_LAYOUT_QA=on` 的 `UNTRANSLATED_PARAGRAPH`（译文与源文同页逐字相同的整段外文）或 `plan080_trace_report.py` 核对。
2. **剂量口径走确定性映射**：`Q2W→每2周一次`、`Q4W→每4周一次`；禁止模型自由表达成「每周两次」。
3. **药名走 glossary 白名单 + `detect_drug_name_drift` 黑名单双向兜底**；常见伪译（特罗金单抗）直替为曲罗芦单抗。
4. **嵌套剂量式必须塌回短写**，中文数词形（`每四周一次（每 4 周一次（Q4W））`）也要覆盖。
5. **角标**：文本层会把 `m²` 压平成 `m2`；译后对单位后的 `2/3` 还原为 `² ³`，数字比对视 `²≡2`。不碰 `IL-2`、`M2`、`EASI-75`。负指数 `mL⁻¹` 字体无字形，保持 `mL-1`。
6. **括号里有字的格要翻译**：`3 (Moderate)`→`3（中度）`；括号内只有数值才是数据格。
7. **QA 比对先去零宽字符**（`U+200B/200C/200D/2060/FEFF/00AD`）并丢弃换行截断的网址前缀碎片；低风险术语「译名未出现」默认不报，高风险（药名/适应症）必报。总入口 [SK-Q012](../translation-playbook/SKILL.md)。

| 症状 | 先查 | 修法 | 判据 |
| --- | --- | --- | --- |
| 每周两次（Q2W） | sanitize 是否含 `_DOSE_CALQUES` | 确定性替换 | 输出计数=0 |
| 特罗金单抗 | `_DRUG_CALQUES` | 直替曲罗芦单抗 | 计数=0 |
| 发现gs | Fallback 残留 | 去 gs 碎片 | 计数=0 |
| Fallback: 12 | il_translator 日志 | 重译+校验 | Fallback 残留=0 |

## 相关文件

- `qyunslation/structure/text_sanitize.py`
- `scripts/apply-pdf2zh-045c-sanitize.py`
