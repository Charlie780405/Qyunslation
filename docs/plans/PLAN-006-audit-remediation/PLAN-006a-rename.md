# PLAN-006a：彻底重命名

- `docutranslate` → `qyunslation`（421 import / pyproject / spec / Dockerfile / vite）
- 环境变量双读：`QYUNSLATION_*` 优先，回落 `DOCUTRANSLATE_*`
- 删除 symlink 依赖与旧 editable 安装
