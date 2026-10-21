# WT-085：横向表整页转正翻译、表内汉字字重、符号字形不再阻断（实施走查）

样张：MG-K10（50-LIT-2026-MGK10-Trial.pdf），第 6–7 页横向表 2、第 5/9 页表 1/3、第 2 页项目符号。

| 项 | 结论 | 做法 |
| --- | --- | --- |
| 乱码阻断（项目符号/页眉分隔符） | 已修 | `symbol_glyph_evidence`：页上所有 C0/U+FFFD 都独占词位且无 C1/mojibake → 警告 `TEXT_LAYER_SYMBOL_GLYPH`；字中间的乱码仍阻断 |
| 横向表整页没翻译 | 已修 | `pdf_rotate`：翻译前内容流转正（`cm`），译后 `show_pdf_page(rotate)` 转回；双语左半换回原件；页脚/页码盖回原样；开关 `QYUNSLATION_ROTATED_PAGES` |
| 横向表重建 | 已修 | 竖排页边文字不再算表格词；`extend_frame_to_bottom_rule` 数字行占比 0.5→0.4；表题条标签的 U+0003 先转空格 |
| 汉字比数字淡 / 字体不一致 | 已修 | `.env` 的 `QYUNSLATION_FONT` 是可变字体（默认 Thin）。`cjk_font.resolve_static_cjk` 换成静态 Regular/Bold |
| 个别格仍是英文 | 已缓解 | 数字守恒回退前先用新 id 单格重译（`#retry`），绕开错位的缓存 |

## 验证
- 离线：`/tmp/qy/e2e.py 5-7 --post`（真实 pdf2zh_next + 表格后处理 + 转回），mono/dual 第 6、7 页中文、方向正确、页脚在；表 2 两页 `literature_rebuild_painted`。
- 测试：`tests/structure/test_plan085_rotated_tables.py`（7 项）、`test_plan079_encoding.py`、`test_symbol_cmap_dropcap.py`；`-k "table or pdf or qa or runner or literature or encoding or rotate or sanitize or registry or font"` 共 556 项通过。

## 已知限制
- 标签折行被拆成两格（`Difference of means versus` / `placebo, (95% CI)`）时单格译文偏生硬（如 `均值差异与`），根因是按文字行分格；尚未合并续行。
- 批量译文错位在**没有数字**的格上拦不住，只靠重译缓解。
- 转回后的横向页是 `show_pdf_page` 的表单对象，文字仍可提取，但页面内容流不再是 BabelDOC 原样。

## 部署
见提交记录与 `scripts/deploy-translate-stack.sh` 输出（部署后补指纹）。
