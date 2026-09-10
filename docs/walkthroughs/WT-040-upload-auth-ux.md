# WT-040：上传完成态与鉴权白屏

日期：2026-09-10  
纲领：[PLAN-040](../plans/PLAN-040-upload-auth-ux/PLAN-040-upload-auth-ux.md)

## 交付

| 子计划 | 结果 |
| --- | --- |
| 040a | 固定 `cookie_id`；token 落盘；**未登录短登录页**；stale-guard `/config` 与 queue **401** →「请重新登录」 |
| 040b | upload 链 `show_progress=hidden` 用于 dual/prescan；upload settle JS 收起卡住的 Uploading |
| 040c | 本 WT；`verify-plan-040.sh`；补丁序 18–19 |
| 040d | 刷新/关页 **不** 取消翻译；`demo.unload` 只撤销 grace；手动 Stop 仍可取消 |

## 运维

```bash
# 登录后 token 文件
ls -la /home/dev/pdf2zh/gradio.cookie_id /home/dev/pdf2zh/gradio-tokens.json

# 重启后 cookie 名不变；若仍 401，刷新并重新登录一次即可写回 token
systemctl --user restart pdf2zh.service
```

## 验收

```bash
bash scripts/verify-plan-040.sh
```

## 回写

- PLAN-020：登录墙后需 040 处理 401/会话
- WT-038g：auth_file 副作用由 040 承接

## 部署

| 项 | 值 |
| --- | --- |
| merge | `6582850`（040a–d → origin/main） |
| 服务 | `pdf2zh.service`（ExecStartPre 含 040a/b/d） |
| verify-plan-040 | PASS |

