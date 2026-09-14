# WT-060：公司共享专业词库确认工作台

> 计划：[PLAN-060](../plans/PLAN-060-company-termbase-workbench/README.md)
> 工作树：`/home/dev/.cursor/worktrees/qyunslation/plan-060-company-termbase-workbench`

## 工程验证记录

| 项目 | 结果 |
| --- | --- |
| 回环 HMAC、过期/重放拒绝 | 已实现；专项测试通过 |
| 公司项目、普通确认、高风险管理员队列 | 已实现；专项测试通过 |
| 下一文件精确术语复用 | 已实现；专项测试通过 |
| PDF/Office 译前策略注入 | 已实现；补丁及 sidecar 契约测试通过 |
| PDF/DOCX/PPTX/图片 OCR 证据、表格/脚注、参考文献排除 | 已实现；专项测试通过。独立图片、PDF 图像与 Office 内嵌图片先作受上限保护的 OCR 术语解析，避免图内已确认词遗漏译前硬约束。 |
| 快速徽标、专业检查器、单项/批量裁决 | 已实现；补丁在实际上游 GUI 源码内存编译通过 |
| PostgreSQL 迁移、真实浏览器、Caddy 负向验证、泰州 LIVE | 待目标环境执行，不能据此标记完成 |

## 已执行本地命令

```bash
/home/dev/qyunslation/.venv/bin/python -m pytest -q --no-cov \
  tests/workbench/test_plan060_bridge.py \
  tests/workbench/test_plan060_evidence.py \
  tests/ui/test_plan060_workbench_patch.py \
  tests/persist/test_plan060_migration.py \
  tests/persist/test_plan058_candidate.py \
  tests/persist/test_plan058_api.py
```

结果：`29 passed`（含对已安装上游 GUI 的内存补丁编译验证）；Alembic 仅报告既有配置弃用警告。`QYUNSLATION_PLAN060_FULL=1 bash scripts/verify-plan-060.sh` 已通过，并联动通过 PLAN-058、050e、057、059；最终全量回归为 `929 passed, 6 skipped`。

## 待补 LIVE 证据

- 迁移 `060a0001` 在 PostgreSQL 成功；两个服务加载相同且未输出的桥接密钥。
- Caddy 配置不含 `/internal/workbench`，外网请求不可达；sidecar 仍只绑定 loopback。
- 已登录用户在 320、768、1024、1440 宽度下可上传、翻译、打开徽标和确认候选。
- 一份 PDF、DOCX（表格与脚注）、PPTX、图片 OCR、双栏文献分别产生候选；参考文献零候选。
- 普通词在下一文件精确复用且 bge-m3 调用数为零；高风险词仅管理员可终审。
