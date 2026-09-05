# WT-015 翻译进度与一屏布局

## 目标

docx 点「翻译」后右侧预览可见进度；首页左右栏齐平铺满一屏，无外层滚动条。015b：去掉大灰块，空态细描边，底部荃信版权条。

## 根因

- `show_progress_on=[preview]`，docx 时 `preview` 被 `visible=False`，进度无渲染面。
- 预览高度写死 `min(75vh, 720px)`，外层未锁 `100vh`。
- 015 过度拉伸：Group 灰底 + 左栏 `flex:1` + 右栏 `> div` 通配把 hidden 组件撑成空盒。

## 修复

| 项 | 说明 |
|----|------|
| 进度 | `show_progress_on=[preview, preview_html]` |
| 空壳 CSS | 有 `.progress-text` / `.wrap` 时不隐藏 PDF 块 |
| 布局 | `--qy-shell-top` + `--qy-footer-h`；左栏 `flex: 0 0 auto` |
| 空态 | `.qy-col-right::after` 细描边「上传文件后在此预览」 |
| 版权 | `.qy-page-footer`：Qyunslation · 荃信生物 © 2026 |
| docprofile | `allow_custom_value=True` |

## 验证

```bash
bash scripts/verify-plan-015.sh
systemctl --user restart pdf2zh.service
```

手工：

1. 空态：无满屏灰；右栏细描边提示「上传文件后在此预览」；底栏「Qyunslation · 荃信生物 © 2026」
2. 左栏 Type/上传区/按钮为自然高度（上传区约 140–170px）
3. 传 docx → 点翻译 → 右侧进度可见；预览填满后空态描边消失
4. 设置页可内滚且保留面板底色
5. 页面无外层滚动条

浏览器量测（015b，1080p）：Group 透明；上传区 ≈142px；空 PDF `display:none`；`::after` 约满高细描边；版权条高 34px。
