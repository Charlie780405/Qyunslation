# WT-005e 统一入口 — 已启用

**日期：** 2026-08-23  
**状态：** **已做**

## 触发

用户明确要求「在 PDF 界面翻译，不单开域名」→ 满足 PLAN-005e 门禁 #2。

## 实现

| 项 | 做法 |
| --- | --- |
| 上传类型 | `translate.qyunsgen.com` 支持 `.pdf` + `.doc/.docx` + `.png/.jpg/.jpeg` |
| 路由 | PDF 仍走 BabelDOC `:7860`；Word/图片自动调本机 sidecar `:8010` |
| 补丁 | `scripts/apply-pdf2zh-office-route.py`（`pdf2zh.service` ExecStartPre） |
| 公网入口 | **`https://translate.qyunsgen.com`**（唯一用户-facing URL） |
| 旧域名 | `office.qyunsgen.com` 仅 301 兼容，勿再宣传或配置新链接 |
| homepage | 合并为一张「翻译 Qyunslation」卡片 |

## 不变

- BabelDOC 仍为 PDF 后端
- sidecar `:8010` 仍独立运行（仅内部调用）
- PLAN-003/004 质量口径（35b、`temperature=0`、`/no_think`）由 `office.env` 锁定
