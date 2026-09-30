# PLAN-065：专业词汇检查器关闭与入库复用说明

> 状态：**实现中**
> 日期：2026-09-30
> 依赖：PLAN-050 / 056 / 060 / 064
> 验收门：`bash scripts/verify-plan-065.sh`
> Walkthrough：[WT-065](../../walkthroughs/WT-065-inspector-close-reuse.md)

## 一句话

「关闭」真正关掉专业词汇遮罩，并写清：列表是候选，批准入库后下一篇登录翻译自动硬注入。

## 为何新号

PLAN-064 已用于列表裁决。本号只修关闭与文案，不改抽取/裁决/注入算法。

## 施工面

| 项 | 值 |
| --- | --- |
| UI | `pdf2zh_next --gui` Gradio 补丁链 |
| 补丁 | `scripts/apply-pdf2zh-050-workbench.py`、`scripts/apply-pdf2zh-060-termbase-workbench.py` |
| 部署 | `bash scripts/deploy-translate-stack.sh` |

## Out of Scope

- 待确认词自动升正式库
- Vue `frontend/`
- 译前解析 / `hard_constraint` 算法

## 完成定义

- [x] 「关闭」与 Esc 隐藏 Gradio 检查器；JS 抽屉 `data-open=false` 时不占屏
- [x] 文案写清生成 ≠ 入库，入库后下一篇自动复用
- [ ] `verify-plan-065.sh` PASS；浏览器能关面板后点下载
