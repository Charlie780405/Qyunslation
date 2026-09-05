# PLAN-017b 布局打磨：进度左栏 + 双框等高 + 页脚细条

## 目标

修订 PLAN-017 落地后的三处视觉问题：

1. 翻译进度条移到左栏：上传框下方、「翻译选项」上方；空闲零占位，仅翻译中出现。
2. 「当前文档」下拉移到左栏设置区，使中栏原文框与右栏译文框顶底完全对齐、尺寸一致。
3. 底部横贯中+右两栏的细条正中间放 logo + 「Qyunslation · 荃信生物 © 2026」。
4. 原文/译文多页时页码翻页与滚动条一一对应联动。

## 改动

| 文件 | 内容 |
|------|------|
| 补丁 | `scripts/apply-pdf2zh-layout-polish.py`（叠在 dual-preview 之后） |
| 服务 | `scripts/pdf2zh.service`（末位 ExecStartPre） |
| 验收 | `scripts/verify-plan-017b.sh`、`docs/walkthroughs/WT-017b-layout-polish.md` |

## 验收

```bash
bash scripts/verify-plan-017.sh
bash scripts/verify-plan-017b.sh
systemctl --user restart pdf2zh.service
```
