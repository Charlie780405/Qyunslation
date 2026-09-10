# WT-038g：产品抛光

日期：2026-09-10  
纲领：[PLAN-038g](../plans/PLAN-038-gap-closure/PLAN-038g-product-polish.md)

## 交付

| G-ID | 结果 |
| --- | --- |
| G-CAP-005 | **closed**：`apply-pdf2zh-brand.py` 清 `PDFMathTranslate` / `tech_details_string`，SiliconFlow 致谢 `visible=False`+空文案 |
| G-CAP-006 | **closed**：`/home/dev/pdf2zh/auth.csv`（mode 600）+ `config.toml` `auth_file`；Gradio `/config` 未登录 401，`POST /login` 后可取配置 |
| G-CAP-007 | **closed**：`config.toml` 默认 `glossaries`=`proper-nouns,auto-proper-nouns,qx027n` |
| G-CAP-008 | **closed**：`apply-pdf2zh-038g-session-cancel.py`（throughput 之后）；`_ACTIVE_TRANSLATION_TASKS` 按 `session_hash` 隔离 unload 取消 |
| G-CAP-009 | **closed**（DOCX）/ **wontfix**（PPTX）：`scan_docx` 续表 `semantic_id=table:N` + occurrence；PPTX 无跨页续表语义 |

## 运维备注

- 密码在 `auth.csv` 与 `office.env`（`QYUNSLATION_GUI_*`）；**勿提交 git**
- 补丁序见 [`pdf2zh-patch-order.md`](../contracts/pdf2zh-patch-order.md)（038g session-cancel 为第 2 步）

## 验收

```bash
bash scripts/verify-plan-038g.sh
```
