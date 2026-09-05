# WT-009：书信角色字号与中文行款

## 做了什么

1. **OCR 侧（letter only）**：`letter_layout.prepare_letter_boxes` 清洗 `^{th}` /「给药」碎片，写入 debug `role`。
2. **模板字段**：`[letter]` 增加 `body_font_size=12`、`meta_font_size=9`、称谓/落款/页脚字号、`body_first_indent`、`signature_align=right`。
3. **译后排版**：`patch_letter_typesetting` 在 `Typesetting.render_paragraph` 运行时按角色改字号；正文用 BabelDOC `first_line_indent`（不用 U+3000，避免思源映射成 `Ѵ`）；落款右齐；PDF 坐标 `y2` 换算自上而下比例以免地址误判。
4. **GUI**：`apply-pdf2zh-docprofile.py` 在 letter 时调用 patch，并向 HPD 传 `profile=_qy_name`。
5. **Bench V7**：`run_babeldoc_letter.py` 注入 patch 后跑 pdf2zh；产物入 `deliverables/plan-009-letter/`。

## 如何验收

```bash
bash scripts/verify-plan-009.sh after-d
```

门槛：正文中位 ≥11pt；信头/落款中位 ≤ 正文 −1.5pt；段首缩进（字符或视觉）；无 `^{th}` / 孤立「给药」；无扫描底图叠字。

## 风险与降级

- 角色误判：偏右 + 称谓之后双条件；页 1 夹具覆盖。
- BabelDOC 升级导致内部函数更名：patch 返回 False，对齐保持左齐并 warning。
- 中段英文碎句（`similar to US-Vab`）来自 OCR/翻译切分，本 PLAN 不整页重排，未强行合并。
