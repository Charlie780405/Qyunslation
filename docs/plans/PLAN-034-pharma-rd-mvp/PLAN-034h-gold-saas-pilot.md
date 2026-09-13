# PLAN-034h：三类金标闭环与 SaaS 试点

> 状态：**已编码**（OIDC + PWA 壳 + 发布清单 + 端到端门禁；金标全量实跑可 BLOCKED）
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：034a–034g 全部完成
> 验收门：`bash scripts/verify-plan-034h.sh`
> Walkthrough：[WT-034h](../../walkthroughs/WT-034h-gold-saas-pilot.md) · 总览 [WT-034](../../walkthroughs/WT-034-pharma-rd-mvp.md)

## 目标

端到端门禁、响应式 Web/PWA 壳、OIDC 生产适配、部署与回滚清单、WT-034 总验收；证明三类金标在 SaaS 路径上可重复发布。

## 交付（已落地）

1. **端到端门禁** `verify-plan-034h.sh`：OIDC/PWA/清单/SaaS 烟囱必须 PASS；catalog 不齐或未开 `QYUNSLATION_PLAN034_GOLD_E2E` → **BLOCKED**（不冒充 PASS）。伞门 `verify-plan-034.sh` 串 a–h。
2. **PWA**：`manifest.webmanifest` + `sw-034h.js`（仅缓存壳）；挂在 `review.html` / `index.html`。
3. **OIDC**：`OidcAdapter` JWT/JWKS（PyJWT）；`QYUNSLATION_ENV=production` 禁止 Dev 旁路。
4. **部署/回滚**：`plan034h-release-checklist.sh` 指纹；回滚 = 旧 SHA → checklist → `deploy-translate-stack.sh`。
5. **WT-034**：总验收与「FAIL/BLOCKED 不得宣称完成」。

## 判据

- production 下 Dev 旁路不可用；OIDC 缺配置不静默回 Dev。
- SaaS 烟囱：health / projects / review enqueue。
- 金标目录完备或 BLOCKED；全量阈值实跑可选。

## Out of Scope

- App、小程序、计费
- 公开打包 MedDRA
- Vue 主站重构 / 离线翻译
- 自动 merge/push main

## 完成定义

- [x] 端到端门禁脚本（金标 E2E 可 BLOCKED）
- [x] OIDC 生产路径与开发旁路互斥证明
- [x] WT-034 发布；功能分支可合并评审（不自动推 main）
