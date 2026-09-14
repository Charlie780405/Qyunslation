# WT-050f：响应式与无障碍

对应 [PLAN-050f](../plans/PLAN-050-qyunslation-ui-ux/PLAN-050f-responsive-accessibility.md)

- 断点：≥1024 双画布；&lt;1024 单画布切换；&lt;768 左栏堆叠
- 触控目标 `--qy-touch: 44px`
- 键盘：Esc 关检查器；Alt+I 开闭；Alt+1/2 切画布
- `prefers-reduced-motion` 关闭抽屉动画
- live region：`#qy050-dir` polite；状态不按百分比刷屏
- 轮询：应用栏 `setInterval(syncLabels, 2000)` 单一源
