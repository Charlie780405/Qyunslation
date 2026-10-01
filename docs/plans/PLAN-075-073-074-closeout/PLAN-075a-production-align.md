# PLAN-075a：生产对齐

- 074 分支快进合并 `main`；`pg_dump` → `074a0001` → `deploy-translate-stack.sh`。
- 冒烟：`affiliation-segments` / `apply-corrections` 返回 **401**（非 404）。
