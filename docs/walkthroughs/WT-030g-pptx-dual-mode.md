# WT-030g：PPT/PPTX 双模式闭环

## 一、实现概要

1. **扫描器**：[`scan_pptx.py`](../../qyunslation/structure/scan_pptx.py) — 原生路径产出 `TEXT_BOX` / `TABLE` / `IMAGE`（`PPTX_SHAPE`）；图片化路径每页一张全画布 `IMAGE`，`output_editability=RASTERIZED`。
2. **原生执行**：[`pptx_translator.py`](../../qyunslation/translator/ai_translator/pptx_translator.py) 识别 `PICTURE`，不把占位塞进 `texts`；blob 走 `translate_image_bytes`；`.ppt` 先 `prepare_document`。
3. **工作流**：[`pptx_workflow.py`](../../qyunslation/workflow/pptx_workflow.py) 缓存 manifest，译后 `put_execution`。`RENDERED` 渲染页图 → overlay → `pack_image_pptx`。
4. **入口**：`.ppt` 仍路由 `normalize_pptx`；GUI sidecar 补 `.ppt` / `.pptx`。
5. **红灯**：`QY030-PPT-001` 去掉 xfail。

## 二、验证

```bash
bash scripts/verify-plan-030g.sh
.venv/bin/python -m pytest tests/structure/test_scan_pptx.py \
  tests/structure/test_plan030_red_baselines.py::test_pptx_picture_shape_is_emitted_as_a_translatable_object \
  -q --no-cov
```

`verify-plan-028.sh` 单独跑，不从 030g 脚本内嵌套。

## 三、非目标

- SmartArt / Chart / OLE / 动画
- `.ppt` 原样交付
- 跨格式对账 → 030h
