---
name: translate-progress-fullscreen-layout
overview: 修复 Word 翻译时进度条不可见（进度绑在被隐藏的 PDF 预览上），并把首页左右两栏锁成正好一屏高、内部各自滚动。
todos:
  - id: 015-progress
    content: 补丁 show_progress_on=[preview, preview_html]，并给空壳隐藏 CSS 加 progress 例外
    status: completed
  - id: 015-layout-anchor
    content: 给内层 Row 与左右列注入 qy-main-inner-row / qy-col-left / qy-col-right class
    status: completed
  - id: 015-layout-css
    content: 实测 --qy-shell-top，追加一屏锁定 CSS，并保证 settings-container 可内滚
    status: completed
  - id: 015-docprofile
    content: apply-pdf2zh-docprofile.py 给 doc_profile_dropdown 补 allow_custom_value=True
    status: completed
  - id: 015-verify
    content: verify-plan-015.sh + WT-015，restart pdf2zh 后人工确认进度与一屏布局
    status: completed
isProject: false
---

# PLAN-015 翻译进度可见性与一屏布局

## 背景与根因

翻译并没有失效。点击后 sidecar 已接单并正常推进（日志 `[61%] 正在翻译 (22/42)`，任务 `7e73275bf6bc4e10`），office-route 也在按 2 秒轮询回填 `progress(pct, desc=...)`。

问题出在进度的**渲染位置**：

```6790:6791:/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py
            uploaded_files_view,  # Uploaded files view
            ],
            show_progress_on=[preview],
```

PLAN-014 为了修 Word 预览空白，把 docx 场景下的 `preview`（`PDF()` 组件）设成了 `visible=False`。进度条挂在隐藏组件上，前端就完全没有反馈，看起来像"点了没反应"。

布局方面，预览高度是写死的 `height: min(75vh, 720px)`（`.pdf-preview-fixed`）和 `max-height: min(70vh, 820px)`（`.qy-html-preview-wrap`），外层 `.tab-main-row` 没有高度约束，所以两栏都短于一屏且整页可滚。

```mermaid
flowchart LR
  click["点击翻译"] --> route["office-route 调 sidecar"]
  route --> prog["progress(pct, desc)"]
  prog --> tracker["StatusTracker 渲染到 show_progress_on 组件"]
  tracker --> hidden["preview visible=False（docx）"]
  hidden --> nothing["前端无任何反馈"]
```

## 改动

全部改动落在幂等补丁脚本里（gui.py 位于 uv tools 目录，不入库），由 [scripts/pdf2zh.service](scripts/pdf2zh.service) 的 `ExecStartPre` 链自动重放。

### 1. 进度条同时绑定两个预览组件

在 [scripts/apply-pdf2zh-office-preview.py](scripts/apply-pdf2zh-office-preview.py) 新增一段补丁：

- 把 `show_progress_on=[preview],` 替换为 `show_progress_on=[preview, preview_html],`；以 `preview_html]` 是否已出现作幂等判据。
- PDF 场景 `preview` 可见、`preview_html` 隐藏；docx/图片场景反之。两者都列上，总有一个能渲染进度。

同时给 PLAN-014 加的空壳隐藏规则开个例外，避免翻译期间 PDF 块因暂时没有 canvas 被 CSS 抹掉：

```
.pdf-preview-fixed:not(:has(canvas)):not(:has(iframe)):not(:has(embed)):not(:has(.progress-text)):not(:has(.wrap))
```

### 2. 首页锁定一屏，左右栏各自内滚

内层 Row 目前没有 class，先在补丁里补上锚点：

```5319:5320:/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py
                    with gr.Row():
                        with gr.Column(scale=1):
```

改为 `gr.Row(elem_classes=["qy-main-inner-row"], equal_height=True)`，左列加 `elem_classes=["qy-col-left"]`，右列（`scale=2`）加 `elem_classes=["qy-col-right"]`。

CSS 追加到 `.qy-html-preview-wrap` 之后（同特异性、后者胜）：

- `:root { --qy-shell-top: <实测值>px; }` — 品牌栏 + 容器 padding 的总高，用浏览器量 `.tab-main-row` 的 `getBoundingClientRect().top` 后写死。
- `.tab-main-row { height: calc(100vh - var(--qy-shell-top)) !important; overflow: hidden !important; }`
- `.qy-main-inner-row { height: 100% !important; align-items: stretch !important; min-height: 0 !important; }`
- `.qy-col-left { height: 100% !important; min-height: 0 !important; overflow-y: auto !important; overflow-x: hidden !important; }`
- `.qy-col-right { height: 100% !important; min-height: 0 !important; display: flex !important; flex-direction: column !important; }`
- `.qy-col-right .pdf-preview-fixed { flex: 1 1 auto !important; height: auto !important; max-height: none !important; min-height: 0 !important; }`
- `.qy-col-right .qy-html-preview-wrap { flex: 1 1 auto; height: auto; max-height: none; min-height: 0; overflow: auto; }`

**风险点（必须一起处理）**：设置页 `tab_settings` 与 `tab_main` 同在被锁高的列内，`overflow: hidden` 会让长设置表单无法滚动。补一条 `.settings-container { max-height: 100% !important; overflow-y: auto !important; }`，并在验收里单独走一遍设置页。

### 3. 顺带修 doc_profile 下拉的硬报错

日志里已复现（12:11:49）：

```
gradio.exceptions.Error: "Value: 自动（识别为：通用） is not in the list of choices: ['自动', '正式书信', '学术文献', 'IND递交资料', '通用']"
```

`_qy_hint_doc_profile` 会把下拉值写成 `hint_choice()` 返回的 `自动（识别为：X）`，但 `doc_profile_dropdown` 没开 `allow_custom_value`，而该下拉又是它自己的 input，所以**上传第二个文件时必然抛错**。在 [scripts/apply-pdf2zh-docprofile.py](scripts/apply-pdf2zh-docprofile.py) 给该 Dropdown 补 `allow_custom_value=True`。

这条不影响翻译按钮（`doc_profile_dropdown` 不在 `ui_setting_controls` 里），但属于同一屏交互的既有缺陷，一并修掉。

## 验证

- 新增 `scripts/verify-plan-015.sh`：断言 gui.py 含 `show_progress_on=[preview, preview_html]`、`qy-main-inner-row`、`--qy-shell-top`、doc_profile 处的 `allow_custom_value=True`；再各跑一次 apply 脚本确认输出 `already patched`（幂等）。
- 新增 `docs/walkthroughs/WT-015-progress-fullscreen.md`，手工项：restart pdf2zh → 传 docx 点翻译，进度条可见且百分比走动 → 页面无外层滚动条，左右栏齐平铺满一屏 → 左栏内容超长时自身可滚 → 设置页可滚 → 传 PDF 回归预览与进度。
- 部署按既有流程：精确 commit、no-ff merge main、推远程、`systemctl --user restart pdf2zh`。

## 不做

- 不改 sidecar 的翻译逻辑与轮询间隔。
- 不在按钮下方另加常驻状态条（已选定只用预览区进度）。
- 不动移动端断点适配。