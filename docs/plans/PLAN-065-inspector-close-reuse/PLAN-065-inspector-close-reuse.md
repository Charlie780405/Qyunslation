# PLAN-065：检查器关闭与入库复用说明

> 父目录：[README](./README.md)

## 问题

1. 「关闭 / 返回列表」只收详情，不关 `qy_inspector`。060 CSS 把检查器做成全屏遮罩，下载/预览被挡住。
2. JS 抽屉 `#qy050-inspector` 同样带 `qy-050-inspector`，没有 `[data-open="false"] { display: none }`，关闭只改属性。
3. 用户误以为译后词表已入库。实际：抽取 → pending → 人工批准 → 下一篇 `hard_terms` 注入。

## 改动

- `_qy060_close_inspector` 写 `qy_insp_on=False` 并 `visible=False`。
- 顶部增加始终可见的「关闭」；Esc 点该按钮。
- `#qy050-inspector[data-open="false"] { display: none !important; }`
- 全屏 fixed 只作用于 Gradio 检查器：`.qy-050-inspector:not(#qy050-inspector)`
- 空态/入库成功文案写清下一篇自动硬注入。

## 验证

```bash
bash scripts/verify-plan-065.sh
```
