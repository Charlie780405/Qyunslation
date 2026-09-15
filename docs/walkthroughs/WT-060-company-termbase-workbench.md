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

## 生产部署记录（2026-09-15）

- 已将 `main` 精确推进至 `f26fbbad39359a768249b6ea5abd2123782c048e` 并推送至 `origin/main`。
- PostgreSQL 已执行 `060a0001` 迁移；桥接密钥、工作台租户和管理员令牌仅写入受保护的部署环境文件，未进入源码、补丁、日志或 Git。
- 公共 Caddy 配置不含 `/internal/workbench` 路由并通过配置校验。真实侧车仍仅监听回环地址：未签名本地请求返回 `401`，公网同一路径返回 `404`。
- `pdf2zh.service` 与 `qyunslation-office.service` 已重启且均为 `active`；翻译栈部署指纹一致。
- `QYUNSLATION_PLAN060_LIVE=1 bash scripts/verify-plan-060.sh`：静态、专项测试、迁移、Caddy 负向验证和部署变量均为 `PASS`；四视宽浏览器证据缺失，结果为 `SUMMARY: BLOCKED`（`blocked=1`、`fail=0`）。因此功能已部署，但 PLAN-060 不得标记完成。

## 待补 LIVE 证据

- 迁移 `060a0001` 在 PostgreSQL 成功；两个服务加载相同且未输出的桥接密钥。
- Caddy 配置不含 `/internal/workbench`，外网请求不可达；sidecar 仍只绑定 loopback。
- 已登录用户在 320、768、1024、1440 宽度下可上传、翻译、打开徽标和确认候选。
- 一份 PDF、DOCX（表格与脚注）、PPTX、图片 OCR、双栏文献分别产生候选；参考文献零候选。
- 普通词在下一文件精确复用且 bge-m3 调用数为零；高风险词仅管理员可终审。

## 追加验证记录（2026-09-15，PLAN-060 UI/生产收口）

- `main` 已推进并推送至 `4cffa84e2a0915f7cfae0ef2270b7b681b57eb37`，新增浏览器字体别名修复，避免 Gradio 生成 CSS 请求不存在的本地字体资源。
- `bash scripts/deploy-translate-stack.sh` 已重新部署生产翻译栈：`pdf2zh.service` 与 `qyunslation-office.service` 均为 `active`，sidecar 本地/远端能力指纹一致。
- 四视宽浏览器验证证据：`/home/dev/tmp-bridge/qy-plan060-browser-after-fonts-7gaQhV/browser-evidence.json`。
  - 320、768、1024、1440 宽度下 `documentWidth == viewportWidth`。
  - “就绪”文字可见且为白色高对比色 `rgb(255, 255, 255)`。
  - 翻译按钮在四个宽度下均可见。
  - 字体资源 `404` 已清零，HTTP 4xx/5xx 为 `0`。
  - 仍存在每个宽度一次的 Gradio/HuggingFace `postMessage` origin warning；未观察到业务接口错误，暂作为上游残留 warning 记录。
- PLAN-060 LIVE 门禁：
  - `QYUNSLATION_PLAN060_LIVE=1` + 浏览器证据运行后，静态、迁移、桥接变量、浏览器证据均为 `PASS`。
  - 当前主机未发现可供验证的 Caddy 配置文件或 `caddy.service`，因此“内部接口未被 Caddy 暴露”的负向断言按规则为 `BLOCKED`；最终 `SUMMARY: BLOCKED blocked=1 fail=0`。
- 依赖门禁：
  - `QYUNSLATION_PLAN060_FULL=1 bash scripts/verify-plan-060.sh` 通过，联动 PLAN-058、PLAN-050e、PLAN-057、PLAN-059 均为 `PASS`。
- 生产内网术语闭环证据：`/home/dev/tmp-bridge/qy-plan060-live-term-STAUuN/live-term-closure.json`。
  - 普通候选初始状态 `pending`、风险 `normal`。
  - 使用测试账号身份批准后状态为 `approved`。
  - 下一次译前同一术语精确命中并返回硬约束译法，`semantic_used=false`，证明相同已确认术语复用不依赖 bge-m3。
- 真实文献 UI 端到端验证仍未通过：
  - 样本 `CBP-201 Ph 3.pdf` 曾在浏览器中成功上传并启动翻译，但 363.2 秒后停留在 `已处理 图 0/0 · 表 0/0 - 97.3%`。
  - 日志显示主 PDF 文本翻译已完成，随后图片/OCR 后处理多次触发 QC warning/fail，未进入“翻译完成后展示专业词汇候选清单”的 UI 状态。
  - 因此“完成一篇真实文献后在界面展示待确认候选列表”仍为 `BLOCKED`，不能标记 PLAN-060 完成。建议后续将术语候选提取前移到文本翻译完成点，或在 manifest 显示无 Figure/Table/OCR occurrence 时跳过不必要图片后处理，避免术语面板被图片流程阻塞。
