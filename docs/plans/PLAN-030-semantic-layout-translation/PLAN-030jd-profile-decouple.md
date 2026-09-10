# PLAN-030jd：D5 画像与容器解耦

> 状态：**已完成**
> 父计划：[PLAN-030j](./PLAN-030j-layout-debt.md)
> 验收门：`bash scripts/verify-plan-030j.sh`

## 交付

- `profiles.suggest_content_profile()` 按 Figure/Table 题注计数推断
- `scan_pdf` / `scan_docx` 共用；支持 `content_profile` 用户覆盖
- parity 夹具 PDF/DOCX 同为 `RESEARCH_ARTICLE`
