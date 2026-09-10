# PLAN-038g：产品抛光

> 状态：**已完成**
> 父计划：[PLAN-038](./PLAN-038-gap-closure.md)
> 归属缺口：G-CAP-005…009
> 验收门：`bash scripts/verify-plan-038g.sh`
> Walkthrough：[WT-038g](../../walkthroughs/WT-038g-product-polish.md)

## 交付矩阵

| G-ID | 项 | 结果 |
| --- | --- | --- |
| G-CAP-005 | Gradio 全面白牌 | `apply-pdf2zh-brand.py`：标题/页眉页脚 Qyunslation；SiliconFlow 致谢隐藏 |
| G-CAP-006 | `--auth-file` 登录墙 | `auth.csv` + `gui_settings.auth_file`；`/config` 401，`POST /login` 后放行 |
| G-CAP-007 | 术语表 `--glossaries` | config 默认 `proper-nouns,auto,qx027n` |
| G-CAP-008 | 多租户 unload 互取消 | `apply-pdf2zh-038g-session-cancel.py`（throughput 后）按 session 隔离 |
| G-CAP-009 | DOCX/PPTX 跨页续表 | DOCX `continued_table_caption_num` + occurrence；PPTX → wontfix |

## 非目标

- 不 fork Gradio / BabelDOC
- 不把 `auth.csv` 密码提交进 git
