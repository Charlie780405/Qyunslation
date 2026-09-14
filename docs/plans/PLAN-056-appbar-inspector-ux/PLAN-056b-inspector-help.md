# PLAN-056b：检查器/帮助可见性

> 父计划：[PLAN-056](./PLAN-056-appbar-inspector-ux.md)

## 目标

去掉 `.qy-050-inspector` 的 `position:fixed` + `transform:translateX(100%)`；帮助与检查器改为应用栏下 Accordion，按钮切换 `open`。

## 交付

| 项 | 要求 |
| --- | --- |
| CSS | 无 `translateX(100%)` 抽屉 |
| 帮助 | `gr.Accordion`，默认 `open=False` |
| 检查器 | 同上；文案：预扫描在左栏、QA 阻断不挡审阅稿、TM 仅精确 reuse |
| 红线 | `apply_js` 空操作；禁止写回 `js=` / `head=` |

契约 `ui-runtime-050.md`：`.qy-050-inspector` = 应用栏下 Accordion。

## 完成定义

- [x] 补丁与现网 `gui.py` 均无抽屉位移 CSS
- [x] 点「检查器」可在 Logo/顶栏下看到正文
