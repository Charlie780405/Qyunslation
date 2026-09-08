# WT-031 仓库专业治理

**日期：** 2026-09-08  
**状态：** 代码与 GitHub 治理已完成；生产进程未因本 PLAN 重启（品牌未切到现网 sidecar）  
**分支：** `feat/PLAN-031-repo-governance`

## 做了什么

- GitHub `Charlie780405/Qyunslation` 改为 **Private**；About：`荃信内部文档翻译。派生自 xunbu/docutranslate（MPL-2.0）。`；Wiki / Projects 关闭。
- 删除相对 `main` 为 **0 ahead** 的 13 个过期 `feat/plan-*` / `feat/PLAN-*`。保留 `main` 与 `codex/recovery-030e-030f-20260908`（1 ahead）。
- Remote：`origin` → 本仓；原 `origin`（xunbu/docutranslate）改名为 `upstream`；保留 `qyunslation` 与 `mirror`（其它 worktree 仍跟踪 `qyunslation/main`）。
- 新增 [NOTICE.md](../../NOTICE.md)；LICENSE 未改。
- README 四份改为 Qyunslation 内部说明 / 短跳转；根目录 `DocuTranslate.*` 移入 `archive/legacy/`。
- i18n、贡献弹窗、CLI/Web 启动语、markdown 页脚、Dockerfile LABEL、`.env.example` 文件头、PyInstaller 产出名、MCP README 安装命令收口。

## 怎么验

```bash
bash scripts/verify-plan-031.sh
```

2026-09-08 实跑：`PASS=30 FAIL=0`；`import qyunslation.app` → 1.7.8。

## 线上

未重启 `qyunslation-office.service` / `pdf2zh.service`。本 PLAN 不改端口与路由。现网 `https://translate.qyunsgen.com` 返回 **200**。合并并重建前端静态资源、重启 sidecar 后，8010 Web 标题才会变成 Qyunslation。

## 回滚

- 可见性：`gh repo edit Charlie780405/Qyunslation --visibility public --accept-visibility-change-consequences`
- 品牌：revert 本分支提交
- 已删 0-ahead 分支：本地若仍有同名 ref 可再 push；远程已删

## 未沉淀原因

一次性仓库治理，不构成可重复工作流，不新建 Skill。
