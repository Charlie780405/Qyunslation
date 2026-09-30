# WT-066：临床翻译工作台运行层发布证据

> 对应计划：[PLAN-066](../plans/PLAN-066-clinical-workbench/README.md)
> 发布范围：运行层、BFF/TranslationRun 数据迁移、PDF 独立 runner、预览校验和术语筛选记录。

## 提交与远程

本次精确提交并推送到 `origin/main` 的提交为：

- `e3ee4ab` `fix: harden PDF preview rendering and verification`
- `009bbda` `chore: extend clinical term screening decisions`
- `364e2c7` `test: scope preview guard verification`
- `f937347` `fix: use project interpreter for release gate`

本地 `HEAD` 与 `origin/main` 均为 `f93734737f0c`。

`.cursor/mcp.json` 和 `slide-deck/` 是本机 IDE 配置及生成的演示二进制，未纳入提交或部署。

## 生产部署

执行：

```bash
bash scripts/deploy-translate-stack.sh
```

结果：

- `pdf2zh.service`：`active`
- `qyunslation-office.service`：`active`
- sidecar 健康检查：HTTP 200
- 本地/sidecar 代码指纹：`7542777de0fd`，一致
- `http://127.0.0.1:7860/`：HTTP 200（服务预热后）
- `https://translate.qyunsgen.com/`：HTTP 200

数据库在受保护部署环境中从 `063a0001` 前进到 `066e0002`（head），执行了 066a、066c、066e0001、066e0002 四个向前迁移；未执行回滚或破坏性清理。

## 验证结果

- `bash scripts/verify-plan-066.sh`：PASS
- `bash scripts/verify-plan-020.sh`：PASS
- 预览/检查器聚焦测试：`21 passed`
- 完整发布门禁：`passed=7, failed=2, blocked=4`
  - 失败为既有 038g/040 现场检查，不由本次提交引入。
  - 阻断为未提供 041、042、044、033l 历史真实样本；未伪造样本通过。

## 发布边界与回滚

当前公网 Caddy 仍将根路径交给 Gradio：`/next`、`/app-assets`、`/auth` 和 `/api/v1` 尚未执行 PLAN-066k 灰度路由切换，因此公网 `/next/login` 与 `/api/v1/health` 返回 404 属于未切换状态，不判定为 Vue 公网验收通过。

如需回滚本次运行层发布，使用既有入口切换并保留数据库和任务数据；不要删除 066 迁移、重复执行任务或清理旧产物。服务代码回退后需重新执行 `scripts/deploy-translate-stack.sh` 并复核指纹与健康检查。
