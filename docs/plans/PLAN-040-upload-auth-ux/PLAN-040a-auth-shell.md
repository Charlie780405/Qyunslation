# PLAN-040a：鉴权壳

> 状态：**已完成**
> 父计划：[PLAN-040](./PLAN-040-upload-auth-ux.md)

## 交付

- `scripts/apply-pdf2zh-040a-auth-shell.py`
  - 固定 `App.cookie_id` ← `QYUNSLATION_GRADIO_COOKIE_ID` 或 `/home/dev/pdf2zh/gradio.cookie_id`
  - token 字典落盘 `/home/dev/pdf2zh/gradio-tokens.json`
  - 未登录 `GET /`：**短登录页**（非 349KB Gradio 壳）
  - `auth_message` 中文登录提示
  - stale-guard：`/config` 401 →「请重新登录」横幅

## 验收

`bash scripts/verify-plan-040.sh`（含 040a 断言：短页 `<50KB`、登录后整页壳）
