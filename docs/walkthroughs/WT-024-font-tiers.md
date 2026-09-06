# WT-024 全屏裁切修复与字号层级统一

## 交付

- 全屏克隆不再嵌套 `.qy-viewer-inner`；`height:100%` + `calc(100vh-72px)`
- `_assign_tiers` + `_assign_tier_sizes`：组内统一、组间比例、outlier 降级
- QC C7a/C7b；SK-Q002 铁律更新
- `verify-plan-024.sh` 验收

## 部署

- 分支：`feat/plan-024-font-tiers`
- 合并：`--no-ff` → `main`
- 服务：`pdf2zh.service` + `qyunslation-office.service`
- 生产哈希：（合并后回填）
