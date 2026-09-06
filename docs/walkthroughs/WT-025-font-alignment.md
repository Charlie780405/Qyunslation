# WT-025 译文对齐锚定原图墨迹

## 做了什么

- [`qyunslation/extensions/image_translate.py`](../../qyunslation/extensions/image_translate.py)：`_ink_geometry` / `_infer_align`、主行墨迹锚点渲染、C8、`ALIGN_TOL_PX`
- SK-Q002：铁律 8–11/15 改为墨迹锚点；pitfalls #20/#21；reference 对齐表
- [`scripts/verify-plan-025.sh`](../../scripts/verify-plan-025.sh)

## 验证

```bash
bash scripts/verify-plan-025.sh
```

期望：C8 全绿；期标题 `plan_dx/plan_dy≈0`；W12–W52 竖向方差 ≤2px。

## 已知边界

超长英文贴图像左缘时（如「分层因素」→ Stratification factors）会水平 clamp，`plan_dx` 可 >8，C8 仍以计划锚点为准。
