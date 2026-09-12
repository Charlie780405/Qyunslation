---
name: translation-content-integrity
description: >-
  译文内容完整性：Fallback 段落、拉丁残留、药名漂移、剂量口径 Q2W/Q4W。
  触发：漏翻译、译文里有英文、Fallback to simple translation、药名不对、
  剂量口径、Q2W、Q4W、每周两次、特罗金、发现gs、拉丁残留、术语不一致、PLAN-047d。
---

# 译文内容完整性（SK-Q007）

## 铁律

1. **日志 `Successful/Fallback` 计数必须进 verify**——Fallback 段落单独重译并校验残留拉丁串。
2. **剂量口径走确定性映射**：`Q2W→每2周一次`、`Q4W→每4周一次`；禁止模型自由表达成「每周两次」。
3. **药名走 glossary 白名单 + `detect_drug_name_drift` 黑名单双向兜底**；常见伪译（特罗金单抗）直替为曲罗芦单抗。
4. **嵌套剂量式必须塌回短写**，中文数词形（`每四周一次（每 4 周一次（Q4W））`）也要覆盖。

| 症状 | 先查 | 修法 | 判据 |
| --- | --- | --- | --- |
| 每周两次（Q2W） | sanitize 是否含 `_DOSE_CALQUES` | 确定性替换 | 输出计数=0 |
| 特罗金单抗 | `_DRUG_CALQUES` | 直替曲罗芦单抗 | 计数=0 |
| 发现gs | Fallback 残留 | 去 gs 碎片 | 计数=0 |
| Fallback: 12 | il_translator 日志 | 重译+校验 | Fallback 残留=0 |

## 相关文件

- `qyunslation/structure/text_sanitize.py`
- `scripts/apply-pdf2zh-045c-sanitize.py`
