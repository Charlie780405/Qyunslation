# PLAN-057a：隐藏语言行与帮助/检查器双入口

> 父计划：[PLAN-057](./PLAN-057-chrome-dedupe.md)

## 目标

只留顶栏 `qy_dir` / 帮助 / 检查器按钮；左栏 `lang_from`/`lang_to` 仍存在并与 `qy_dir` 同步，但对用户不可见。

## 交付

- `lang-row`：`visible=False`（或 CSS 藏）
- 帮助/检查器：`gr.Column(visible=False)`，按钮 `click` → `gr.update(visible=...)`
- 标记 `# _qy_057_appbar_begin/end`，可替换 056 块

## 完成定义

- [x] 无 `qy_help = gr.Accordion` / `qy_inspector = gr.Accordion`
- [x] 顶栏按钮可开关面板；左栏无语言下拉
