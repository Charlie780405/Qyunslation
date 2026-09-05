# WT-015 翻译进度与一屏布局

## 目标

docx 点「翻译」后右侧预览可见进度；首页左右栏齐平铺满一屏，无外层滚动条。

## 根因

- `show_progress_on=[preview]`，docx 时 `preview` 被 `visible=False`，进度无渲染面。
- 预览高度写死 `min(75vh, 720px)`，外层未锁 `100vh`。

## 修复

| 项 | 说明 |
|----|------|
| 进度 | `show_progress_on=[preview, preview_html]` |
| 空壳 CSS | 有 `.progress-text` / `.wrap` 时不隐藏 PDF 块 |
| 布局 | `--qy-shell-top: 104px` + `.qy-col-left/right` 内滚 |
| docprofile | `allow_custom_value=True`（避免「自动（识别为：…）」硬报错） |

## 验证

```bash
bash scripts/verify-plan-015.sh
systemctl --user restart pdf2zh.service
```

`verify-plan-015.sh`：**15/15 PASS**（2026-09-05）

浏览器量测（1080p）：

- `.tab-main-row` top≈102.5、高 976 → 铺满剩余视口；`document` 无外层滚动
- `.qy-col-left` / `.qy-col-right` 高 ≈974
- 设置页：`.settings-container` `overflow-y: auto`，内容可内滚
- Group `.hide` 不被 `display:flex` 覆盖

手工：

1. 传 docx → 点翻译 → 右侧预览出现进度且百分比走动
2. 页面无外层滚动条；左右栏齐平铺满一屏
3. 左栏内容超长时自身可滚
4. 设置页可滚
5. 传 PDF → 预览与进度回归正常
