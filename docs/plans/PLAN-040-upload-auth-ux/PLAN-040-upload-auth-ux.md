# PLAN-040：上传完成态与鉴权白屏

> 状态：**已完成**
> 日期：2026-09-10
> 批准记录：用户确认 Cursor 计划「PLAN-040 上传鉴权」后实施
> 验收门：`bash scripts/verify-plan-040.sh`；总览 [WT-040](../../walkthroughs/WT-040-upload-auth-ux.md)
> 前置：PLAN-020 stale-guard；PLAN-038g auth_file

## 一、目标

1. 未登录可见明确登录页/横幅，禁止「整页壳 + /config 401」白屏
2. `cookie_id` 稳定 + token 落盘，重启后同 cookie 仍可会话（或明确要求重登）
3. File Uploading 与长链 prescan 解耦；prescan 只更新状态条
4. `/config` 401 时 stale-guard 提示重新登录

## 二、子计划

| 编号 | 文件 | 交付 |
| --- | --- | --- |
| [040a](./PLAN-040a-auth-shell.md) | 鉴权壳 | cookie_id + token 持久化 + 401 横幅 |
| [040b](./PLAN-040b-upload-settle.md) | 上传完成态 | Uploading 与 prescan 拆开 |
| [040c](./PLAN-040c-docs-verify.md) | 文档验收 | verify + WT + 补丁序 |
| [040d](./PLAN-040d-refresh-keep.md) | 刷新保活 | unload 不杀任务；仅手动 Stop |

## 三、非目标

- 不关 Cloudflare / 不撤 auth_file / 不关 no-store
- 不做 Office 进度 18.5%（另开）

## 四、完成定义

- [x] 未带 cookie：`GET /` **短登录页**（非整棵壳），可见登录表单
- [x] 重启后同 cookie_id；token 文件存在则 `/config` 可 200
- [x] File Uploading 不绑死在 tier2/3
- [x] 刷新不杀进行中翻译；仅手动 Stop 取消
- [x] `verify-plan-040.sh` PASS
