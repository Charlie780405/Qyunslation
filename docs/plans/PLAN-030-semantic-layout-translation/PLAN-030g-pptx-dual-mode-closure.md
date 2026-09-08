# PLAN-030g 子计划：PPT/PPTX 双模式纵向闭环

> 状态：**已完成**
> 日期：2026-09-08
> 批准记录：用户于 2026-09-08 明确批准 PLAN-030g
> 父计划：[PLAN-030](./PLAN-030-semantic-layout-translation.md)（已批准）
> 前置：[PLAN-030e](./PLAN-030e-docx-vertical-closure.md)、[PLAN-030f](./PLAN-030f-image-poster-closure.md)
> 验收门：`bash scripts/verify-plan-030g.sh`（**禁止**嵌套 028/029/030c–030f 全门）

## 目标

关闭父纲领 Checkpoint C 的 PPT 一条：原生可编辑 PPTX 与逐页图片化两条路径都产出 `DocumentStructureManifest`，嵌图有执行三态，`.ppt` 先规范化。

硬验收：

- `QY030-PPT-001` 转绿：合成 `presentation.pptx` 的 picture shape 产出 1 个 `IMAGE`，`execution_status=PENDING`。
- 原生模式：幻灯片数、尺寸、顺序不变；产物可被 python-pptx 打开。
- 图片化模式：每页渲染后走 030f overlay；`output_editability=RASTERIZED`。
- `.ppt`：规范化成功走 PPTX；失败 fail-closed。

## 验证（瘦）

| # | 步骤 | 预期 |
|---|---|---|
| V1 | `compileall` scan_pptx + pptx_workflow + translator | 通过 |
| V2 | `pytest tests/structure/test_scan_pptx.py` + 红灯转绿 | 全绿，无 xfail |
| V3 | `pytest tests/structure --no-cov` **一遍** | 0 xfail |
| V4 | `verify-plan-028.sh` **单独一次** | PASS |

## Out of Scope

- SmartArt / Chart / OLE / 动画
- `.ppt` 原样交付
- 跨格式语义对账（030h）
