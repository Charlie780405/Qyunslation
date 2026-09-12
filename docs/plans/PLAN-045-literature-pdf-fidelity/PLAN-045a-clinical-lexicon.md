# PLAN-045a：皮肤科 / 疗效终点词库

> 状态：已完成
> 父计划：[PLAN-045](./PLAN-045-literature-pdf-fidelity.md)

## 交付

1. `glossaries/clinical-lifecycle.csv` 追加 clear/almost clear、IGA 0/1、EASI-75、Q2W/Q4W、tralokinumab、IMRaD 等短语（禁止孤立 `clear`）。
2. `scripts/glossary_merge_runtime.py` 同步 `merged.csv` → `/home/dev/pdf2zh/glossaries/`。
3. 图片 `_load_glossary` / `_resolve_glossary_path`：未设 env 时默认读仓内或运行时 `merged.csv`。
4. **译后强制**（热修）：校正「皮肤清晰」及 `clear or almost clear` / `tralokinumab` 等短语。**禁止**把 `Q2W`/`Q4W`/`IGA 0/1` 再展成超长短语（会撑爆摘要行框、叠字）。

## 验收

- `tests/glossary/test_plan045_lexicon.py`
- `verify-plan-039.sh` 不回退
