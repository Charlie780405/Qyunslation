# WT-031 仓库专业治理

**日期：** 2026-09-08  
**状态：** 已部署  
**git：** `fe8c144`（merge PLAN-031）+ 前端 static 重建；生产 worktree 已合入并重启 sidecar

## 做了什么

- GitHub `Charlie780405/Qyunslation` 改为 **Private**；About：`荃信内部文档翻译。派生自 xunbu/docutranslate（MPL-2.0）。`；Wiki / Projects 关闭。
- 删除相对 `main` 为 **0 ahead** 的 13 个过期 `feat/plan-*` / `feat/PLAN-*`。保留 `main` 与 `codex/recovery-030e-030f-20260908`（1 ahead）。
- Remote：`origin` → 本仓；原 `origin`（xunbu/docutranslate）改名为 `upstream`；保留 `qyunslation` 与 `mirror`。
- 新增 [NOTICE.md](../../NOTICE.md)；LICENSE 未改。
- README / i18n / 贡献弹窗 / CLI / 页脚 / Dockerfile 等用户可见品牌收口为 Qyunslation。
- 前端 `vite build` 写入 `qyunslation/static`；重启 `qyunslation-office.service`。

## 怎么验

```bash
bash scripts/verify-plan-031.sh
curl -sS http://127.0.0.1:8010/service/meta
curl -sS http://127.0.0.1:8010/static/i18n/zh.json | python3 -c 'import sys,json; print(json.load(sys.stdin)["pageTitle"])'
```

2026-09-08：`PASS=30 FAIL=0`；meta `1.7.8`；`pageTitle=荃信翻译 · Qyunslation`；公网 `translate.qyunsgen.com` → 200。

## 线上

| 项 | 结果 |
|---|---|
| unit | `qyunslation-office.service` active（`:8010`） |
| meta | `{"version":"1.7.8"}` |
| i18n | `荃信翻译 · Qyunslation` |
| 公网 | `https://translate.qyunsgen.com` → 200 |

未改 Caddy / 7860；pdf2zh Gradio 白牌仍由 `apply-pdf2zh-brand.py` 负责。

## 回滚

- 可见性：`gh repo edit Charlie780405/Qyunslation --visibility public --accept-visibility-change-consequences`
- 代码：`git revert` merge `fe8c144` 后重建 static 并 `systemctl --user restart qyunslation-office`

## 未沉淀原因

一次性仓库治理，不构成可重复工作流，不新建 Skill。
