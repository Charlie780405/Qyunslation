---
name: adv options fix
overview: 修复左栏 flex-wrap 导致「高级选项展开后内容与翻译按钮消失」的根因，把高级选项手风琴移到翻译/取消按钮下方并支持内部纵向滚动，同时按你的勾选只隐藏「保存设置」按钮。
todos:
  - id: plan-doc
    content: 写 docs/plans/PLAN-018-adv-options/PLAN-018-adv-options.md
    status: completed
  - id: patch-script
    content: 新增 scripts/apply-pdf2zh-adv-options.py：手风琴移到 action-row 之后 + save_btn visible=False
    status: completed
  - id: css
    content: 追加 _qy_adv_options_css：qy-col-left flex-wrap nowrap、手风琴内容 max-height + overflow-y auto
    status: completed
  - id: service-wire
    content: pdf2zh.service 末位追加 adv-options ExecStartPre 并同步 user unit
    status: completed
  - id: verify
    content: verify-plan-018.sh + 回归 017/017b + 浏览器实测折叠/展开/上传三态
    status: completed
  - id: ship
    content: WT-018 + feat 分支 commit → no-ff merge main → 推远程 → 重启服务验收
    status: completed
isProject: false
---

# PLAN-018 高级选项展开修复与位置下移

## 根因（已在浏览器实测确认）

`.qy-col-left` 的计算样式是 `flex-wrap: wrap`，来自 Gradio 自带规则 `div.svelte-1xp0cw7 > *, div.svelte-1xp0cw7 > .form > * { flex: 1 1 0%; flex-wrap: wrap; ... }`。左栏是 `flex-direction: column` 且高度锁死 907px，高级选项展开后内容总高约 1287px 超出容器，flex 就把溢出项**换行到第二列**渲染：

- 左栏盒子 x 范围 36–394
- 展开后 `.qy-adv-acc` 落在 x=406、y=121，`.action-row`（翻译/取消）落在 x=406、y=777

两者都被推到左栏可视区之外，所以表现为「选项和翻译按钮一起消失」。加 `flex-wrap: nowrap` 后溢出会走 `overflow-y: auto` 正常出滚动条。

## 改动

新增补丁脚本 [scripts/apply-pdf2zh-adv-options.py](scripts/apply-pdf2zh-adv-options.py)，幂等，追加到 [scripts/pdf2zh.service](scripts/pdf2zh.service) 的 `ExecStartPre` 末位（在 `apply-pdf2zh-layout-polish.py` 之后）。

### 1. 手风琴下移到按钮下方

在 `gui.py` 中把整段 `with gr.Accordion("高级选项", ..., elem_classes=["qy-adv-acc"])`（含 `page_range` 到 `save_btn`）从 `doc_profile_dropdown` 之后剪切，粘贴到 action-row 之后：

```python
with gr.Row(elem_classes=["action-row"]):
    translate_btn = gr.Button(...)
    cancel_btn = gr.Button(...)
# <- 高级选项插入到这里
```

两处缩进同为 28 空格，无需重排。手风琴内的 `require_llm_translator_inputs.append(glossary_file)` 与后续 `page_range.select` / `glossary_file.change` / `translate_btn` 输入列表绑定均在文件更靠后位置执行，移动位置不影响 `build_ui_inputs` 的位置映射。

### 2. CSS（新块 `_qy_adv_options_css`，插在 `_qy_layout_polish_css` 之后）

- `.qy-col-left { flex-wrap: nowrap !important; }` — 根因修复
- `.qy-adv-acc > :last-child { max-height: min(44vh, 400px) !important; overflow-y: auto !important; }` — 展开内容超高时内部出上下拖动条，翻译按钮始终保持可见
- `.qy-adv-acc { margin-top: 10px !important; }` 与左栏 `padding-bottom` 微调，避免展开后底部被裁

### 3. 选项取舍（按你的勾选）

保留并可见：页面范围 + 自定义页码框、术语表 CSV、水印模式、忽略缓存、仅输出翻译页、界面语言。

仅隐藏「保存设置」按钮：给 `save_btn = gr.Button(_("Save Settings"), ...)` 追加 `visible=False`。组件保留在 DOM 中，`save_btn.click` 绑定与 `translate_btn` 的位置化输入列表都不受影响。

## 验收

新增 [scripts/verify-plan-018.sh](scripts/verify-plan-018.sh)：手风琴位于 action-row 之后、`save_btn` 带 `visible=False`、CSS 块存在且排在 polish 之后、脚本二次执行幂等、`gui.py` AST 语法通过。

浏览器实测三态：折叠态左栏无滚动条；展开态手风琴在翻译按钮下方、内部出滚动条、翻译/取消按钮仍在原位可见；上传文件后布局与页脚不回归。

## 交付

feat 分支 → 精确 commit → `--no-ff` merge main → 推远程 → `systemctl restart pdf2zh` → 回归跑 `verify-plan-017.sh` / `verify-plan-017b.sh` / `verify-plan-018.sh`，并写 `docs/walkthroughs/WT-018-adv-options.md`。