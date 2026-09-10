---
name: layout polish 017b
overview: 修订 PLAN-017：把「当前文档」下拉与翻译进度槽位都迁到左栏（进度条落在上传框与「翻译选项」之间、空闲时不占位），使中栏原文框与右栏译文框顶底完全对齐、尺寸一致，腾出的底部空间收敛为一条横贯中+右两栏的居中 logo/版权细条。
todos:
  - id: plan-doc
    content: 写 docs/plans/PLAN-017-dual-preview/PLAN-017b-layout-polish.md，并在 PLAN-017 顶部加修订指引
    status: completed
  - id: patch-script
    content: 新增 scripts/apply-pdf2zh-layout-polish.py：把 result_file_selector 与 qy_progress_slot 迁到左栏（进度条位于上传框与「翻译选项」之间）
    status: completed
  - id: css
    content: 追加 _qy_layout_polish_css：进度条空闲零占位（:has(> .wrap:not(.hide))）、中右两栏等高对称、页脚收敛为横贯中+右的居中细条
    status: completed
  - id: service-wire
    content: pdf2zh.service 末位追加 layout-polish ExecStartPre 并同步 user unit
    status: completed
  - id: verify
    content: verify-plan-017b.sh + 回归 verify-plan-017.sh + 浏览器实测空态/翻译中/翻译后三态
    status: completed
  - id: ship
    content: WT-017b + feat 分支 commit → no-ff merge main → 推远程 → 重启服务验收
    status: completed
isProject: false
---

## 背景与现状（实测几何）

- 中栏预览框 `414–1131`，右栏 `1151–1868`；但中栏顶端被「当前文档」下拉压低 96px（框顶 258 vs 右栏 162），右栏底部被进度槽位顶高 48px（框底 996 vs 中栏 1044）。两框既不同高也不同底。
- 进度槽位 `.qy-progress-slot` 现在定义在右栏底部（[apply-pdf2zh-dual-preview.py](/home/dev/qyunslation/scripts/apply-pdf2zh-dual-preview.py) 的 `MID_RIGHT_NEW`），空闲时是一块常驻浅灰卡片。
- 行内页脚 `.qy-inline-footer-col` 实测 `403–1868`，比中栏左边缘 `414` 多出 11px：页脚行 `gap: 1px`，主行 `gap: 20px`。

## 目标形态

```
┌─ 左栏 scale=2 ─┐ ┌─ 中栏 scale=4 ─┐ ┌─ 右栏 scale=4 ─┐
│ Type           │ │ ## 原文        │ │ ## 译文        │
│ [上传框]       │ │ ┌──────────┐  │ │ ┌──────────┐  │
│ 当前文档 ▾     │ │ │          │  │ │ │          │  │  ← 两框顶底完全对齐
│ [进度条*]      │ │ │          │  │ │ │          │  │
│ 翻译选项       │ │ └──────────┘  │ │ └──────────┘  │
│ 语言/模板/高级 │ └────────────────┘ └────────────────┘
│ [翻译][取消]   │      └── 一条横贯中+右：logo + 版权（居中）──┘
└────────────────┘   * 仅翻译中出现，空闲零占位
```

## 实施

### 1. 新增 [scripts/apply-pdf2zh-layout-polish.py](/home/dev/qyunslation/scripts/apply-pdf2zh-layout-polish.py)

叠加在 dual-preview 之后（不改 017 脚本本体，避免对已 patch 的 `gui.py` 做迁移逻辑）。幂等标记 `# _qy_layout_polish`。

- **搬 `result_file_selector`**：从中栏 `## 原文` 之后剪切整段 `result_file_selector = gr.Dropdown(label="当前文档", ...)`，粘到左栏 `uploaded_files_view = gr.Markdown(...)` 之后。中/右栏缩进同为 28 空格，平移即可、无需重排缩进。
- **搬 `qy_progress_slot`**：从右栏底部剪切 `qy_progress_slot = gr.HTML(... elem_classes=["qy-progress-slot"])`，粘到左栏 `gr.Markdown(_("## Translation Options"), ...)` 之前。
- 安全性已核对：`gui.py` 中对 `result_file_selector` 的全部引用都在 9187 行之后的事件绑定里，UI 定义提前到 8064 行不会产生 `NameError`。
- 脚本自带 `verify()`：`compile()` 语法校验 + 断言两个组件各只有一处定义、且位于 `qy-col-left` 与 `qy-col-mid` 之间的文本区间内。

### 2. CSS 块 `/* _qy_layout_polish_css */`（与 dual 同样"先删后插"，插在 dual 之后、`# Build paths to resources` 之前，保证最后生效）

- **进度条空闲零占位**：Gradio 状态条实测是块内直接子元素 `<div class="wrap center full ... hide">`，空闲带 `hide` 类。据此：

```css
.qy-col-left > .qy-progress-slot { display: none !important; }
.qy-col-left > .qy-progress-slot:has(> .wrap:not(.hide)) {
    display: block !important;
    position: relative !important;
    min-height: 44px !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    background: #f8fafc !important;
    overflow: hidden !important;
}
```

- **双栏等高**：`.qy-col-mid, .qy-col-right` 统一 `height:100% / display:flex / flex-direction:column / gap:8px`；两栏子元素结构此时已完全对称（标题 + PDF + HTML + `::after` 空态），顶底自动一致。清掉 dual CSS 里为进度槽位服务的 `order` 补丁残留影响。
- **页脚收敛为一条**：`.qy-inline-footer-row { gap: 20px !important; }` 对齐主行，再用 `.qy-inline-footer-col { margin-left: -4px !important; }` 补掉"页脚只有 1 个间隙、主行有 2 个"导致的 4px 偏差，使细条精确落在 `414–1868`；`.qy-inline-footer` 由现在的仅 `border-top` 改为完整浅描边 + 极浅底 + 高度 ~34px，读作一条独立的 bar，logo 与「Qyunslation · 荃信生物 © 2026」水平垂直居中。

### 3. 接线与验证

- [scripts/pdf2zh.service](/home/dev/qyunslation/scripts/pdf2zh.service) 末位追加 `ExecStartPre=/usr/bin/python3 /home/dev/qyunslation/scripts/apply-pdf2zh-layout-polish.py`，同步到 `~/.config/systemd/user/pdf2zh.service`。
- 新增 `scripts/verify-plan-017b.sh`：断言组件归位、CSS 块存在且在 dual CSS 之后、脚本幂等、`py_compile` 通过、service 含新 ExecStartPre、服务 active。
- 既有 [scripts/verify-plan-017.sh](/home/dev/qyunslation/scripts/verify-plan-017.sh) 不做栏位归属断言，017b 之后仍应全绿，回归时一并跑。
- 浏览器实测三态：空态（两框等高等宽、无进度条、页脚一条）、翻译中（左栏进度条出现且不撑破布局）、翻译后（原文/译文并排、切换「当前文档」两侧同步）。

### 4. 计划文档与交付

- 新增 `docs/plans/PLAN-017-dual-preview/PLAN-017b-layout-polish.md`（沿用 015b 同目录子计划惯例），并在 `PLAN-017-dual-preview.md` 顶部加一行修订指引。
- 新增 `docs/walkthroughs/WT-017b-layout-polish.md`。
- 分支 `feat/plan-017b-layout-polish` → verify 全绿 → 精确 commit → `--no-ff` merge main → 推 qyunslation → 重启 `pdf2zh.service` → 线上验收。