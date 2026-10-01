# PLAN-071c：表格、图片、Logo 与版式修复

> 状态：**待实施**
> 父计划：[PLAN-071](./README.md)
> 依赖：[071b](./PLAN-071b-document-pipeline-manifest.md)

## 目标

将现有图片翻译、表格翻译和图形回填逻辑从 `gui.py` hook 提取为明确的流水线阶段；保证 FDA Logo 等 `PRESERVE` 对象原样复用，正文/地址/签名/附件区不再明显错位或遗漏。

## 现状

| 能力 | 逻辑模块 | GUI 注入 |
| --- | --- | --- |
| Logo/印章回填 | `scripts/graphic_reinsert.py`、`graphic_regions.py` | `apply-pdf2zh-docprofile.py` → `_qy_graphic_reinsert` |
| Letter 重绘 | `scripts/letter_pipeline.py`、`letter_layout.py`、`kv_reinsert.py` | 同 docprofile；`^{th}` 清洗在 `letter_layout.clean_text` |
| 嵌图翻译 | `scripts/pdf_image_translate.py` → `extensions/image_translate.py` | `apply-pdf2zh-docimg.py` `_qy_imgtr_post` |
| 表格翻译 | `scripts/pdf_table_translate.py` + `structure/table_*` | 同 imgtr `_qy_tbltr` |
| 文档画像 | `scripts/doc_profile.py` | `apply-pdf2zh-docprofile.py`（含 BabelDOC typesetting **monkey patch**） |
| 专名 | `scripts/proper_nouns.py` | docprofile 路径 |
| 金标挂接样板 | `gold/plan051_run.py` `_run_postprocess` | — |

新 runner **未调用**上述后处理。邮箱/URL「保护」在 letter 链仅局部（含 `@` 时不做半角→全角），无通用原子 span。

## 任务

### Task 1：迁移为 pipeline stages（保留 scripts 薄封装）

迁入 `qyunslation/pipeline/stages/`（建议文件名）：

- `preserve_graphics.py` ← graphic_regions + graphic_reinsert
- `letter_reflow.py` ← letter_pipeline + letter_layout + kv_reinsert
- `image_overlay.py` ← pdf_image_translate（调用 `extensions/image_translate`）
- `table_translate.py` ← pdf_table_translate / structure table
- `doc_profile.py` ← **仅** detect/apply/resolve 画像配置；**不迁** `patch_*_typesetting` monkey patch（继续由 fingerprint 登记，071a/071i 评估）
- `proper_nouns.py` ← proper_nouns harvest

`scripts/*.py` 改为 re-export/薄封装，保证 Gradio ExecStartPre 旧链路不破。

阶段挂接：`table_figure`（imgtr+tbltr）、`layout`（graphic reinsert + letter reflow 按 profile）。

**验收：** 单元测试用金标路径跑 stage 纯函数；Gradio import 路径 smoke 通过。

### Task 2：PRESERVE 对象策略

- Logo、印章、签名、监管机构标识：`preserve_kind` 已由 Manifest 标注。
- 不发送给翻译模型；保留原始图像或矢量；按原边界框、层级、透明度回填；记录源对象哈希供 QA。
- letter 低置信度时仍执行保护扫描。

**验收：** FDA 样本期望 JSON 中 Logo 哈希与回填后一致；QA 项可检测 Logo 缺失（对接 071e 钩子）。

### Task 3：普通图片与低置信度

- 仅翻译已识别文字标签。
- OCR 置信度低于阈值：保留原图 + warning，禁止臆造文字。

**验收：** 低置信度 fixture 不改像素正文区；产生 warning 结构。

### Task 4：表格锁格与溢出降级

- 先锁定行列、合并单元格、表头、读取顺序和数字列，再按单元格翻译。
- 数字、剂量、单位、百分比、统计符号为保护 token。
- 译文溢出顺序：合理换行 → 列宽调整 → 行高调整 → 受限字号缩放。
- 无法可靠识别结构 → 降级为图片预览 + 要求人工复核（warning/blocker 策略与 071e 对齐：结构不可靠至少 warning，关键场景 blocker）。

**验收：** 表格密集金标行列/合并/数字不变；溢出用例触发降级链且有日志。

### Task 5：原子 span 保护

新增 `qyunslation/pipeline/atomic_spans.py`：

- 邮箱、URL、PIND/IND、Reference ID、法规引用、序数词（含 `th/st/nd/rd`）译前遮蔽、译后还原。
- 接入 text 阶段前后钩子；letter_layout 的 `^{th}` 清洗保留为防御纵深，不再作为唯一手段。

**验收：** fixtures 覆盖 `user@fda.gov`、`www.fda.gov`、`PIND`、`Reference ID`、`20th`；输出无 `^{th}`、无邮箱断裂。

## 数据库 / 接口变更

无新表。Manifest 对象上写齐 `preserve_kind` 与源哈希（依赖 071b）。阶段耗时通过 071d 事件上报。

## 测试文件

- `tests/pipeline/test_preserve_graphics.py`
- `tests/pipeline/test_atomic_spans.py`
- `tests/pipeline/test_table_overflow_fallback.py`
- `tests/pipeline/test_image_low_confidence.py`
- `tests/pipeline/test_letter_reflow_fda_smoke.py`（有样本时）
- 回归：现有 `scripts/test_letter_layout.py`、`scripts/test_kv_reinsert.py` 经薄封装仍可通过

## 完成门槛

- 附图中的 FDA Logo 被原样复用。
- 正文、地址、签名区和附件区不再发生明显错位或遗漏。
- 新流水线不依赖 Gradio DOM/事件队列。

## 验证命令

```bash
pytest -q tests/pipeline/test_preserve_graphics.py tests/pipeline/test_atomic_spans.py \
  tests/pipeline/test_table_overflow_fallback.py tests/pipeline/test_image_low_confidence.py
# 有金标本地路径时：
pytest -q tests/pipeline/test_letter_reflow_fda_smoke.py
```

## 不做

- 不删除 site-packages 补丁；不在本子计划退役 Gradio。
- 不把 BabelDOC typesetting monkey patch 改写为上游 PR（可另立）。
- 不实现审核 UI（071f）与正式导出门禁（071e）。
