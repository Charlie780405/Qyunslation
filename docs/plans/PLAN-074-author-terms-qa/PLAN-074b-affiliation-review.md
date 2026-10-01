# PLAN-074b：研究单位审校与精确 TM

## 交付

- `ReviewSegment` 绑定 `translation_run_id` / `generation` / 页码。
- API：`GET/PATCH .../affiliation-segments`；`POST .../apply-corrections` 创建下一代并写入 `review_overrides`。
- [qyunslation/structure/translation_trace.py](../../../qyunslation/structure/translation_trace.py)：BabelDOC 写回时按源段确定性替换。

## 验收

单位确认无需重跑；修改后新一代 PDF 含修订译名；`tests/structure/test_plan074_translation_trace.py`。
