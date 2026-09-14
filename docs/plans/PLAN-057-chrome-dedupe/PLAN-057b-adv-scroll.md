# PLAN-057b：高级选项可滚与下拉可见

> 父计划：[PLAN-057](./PLAN-057-chrome-dedupe.md)

## 目标

覆盖 019 left-dock 的 `max-height: min(38vh, 340px)`，展开高级后能滚到水印/术语表；下拉不被 `overflow:hidden` 裁切。

## 交付

在 `apply-pdf2zh-050-workbench.py` CSS 追加（不拆 019）：

- `.qy-col-left .qy-adv-acc > :last-child { max-height: min(55vh, 560px); overflow-y: auto; overscroll-behavior: contain; }`
- 打开的 listbox / dropdown `z-index` ≥ 40，`overflow: visible` 兜底

## 完成定义

- [x] 专业→展开高级→滚轮可见水印或术语表
- [x] 页范围等下拉可弹出完整选项
- [x] 翻译/取消始终可见
