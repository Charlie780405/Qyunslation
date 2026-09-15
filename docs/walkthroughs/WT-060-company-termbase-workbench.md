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
| PostgreSQL 迁移、真实浏览器、Caddy 负向验证、泰州 LIVE | PostgreSQL、Caddy 与单篇真实文献工作台已补证；多格式金标与泰州 LIVE 仍需独立验收 |

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

结果：专项范围最新为 `39 passed`（含对已安装上游 GUI 的内存补丁编译验证）；Alembic 仅报告既有配置弃用警告。带实际 Caddy 配置、PostgreSQL 和浏览器证据的 LIVE 门禁为 `SUMMARY: PASS fail=0`，并联动通过 PLAN-058、050e、057、059。

## 生产部署记录（2026-09-15）

- 已将 `main` 精确推进至 `f26fbbad39359a768249b6ea5abd2123782c048e` 并推送至 `origin/main`。
- PostgreSQL 已执行 `060a0001` 迁移；桥接密钥、工作台租户和管理员令牌仅写入受保护的部署环境文件，未进入源码、补丁、日志或 Git。
- 公共 Caddy 配置不含 `/internal/workbench` 路由并通过配置校验。真实侧车仍仅监听回环地址：未签名本地请求返回 `401`，公网同一路径返回 `404`。
- `pdf2zh.service` 与 `qyunslation-office.service` 已重启且均为 `active`；翻译栈部署指纹一致。
- `QYUNSLATION_PLAN060_LIVE=1 bash scripts/verify-plan-060.sh`：静态、专项测试、迁移、Caddy 负向验证和部署变量均为 `PASS`；四视宽浏览器证据缺失，结果为 `SUMMARY: BLOCKED`（`blocked=1`、`fail=0`）。因此功能已部署，但 PLAN-060 不得标记完成。

## 待补 LIVE 证据

- 迁移 `060a0001` 在 PostgreSQL 成功；两个服务加载相同且未输出的桥接密钥。
- Caddy 配置不含 `/internal/workbench`，实际公网请求返回 `404`；sidecar 仍只绑定 loopback。
- 已登录用户在 320、768、1024、1440 宽度下可上传、翻译、打开徽标和确认候选；另有 1440 宽度真实文献验证确认候选面板可见。
- 一份 PDF、DOCX（表格与脚注）、PPTX、图片 OCR、双栏文献分别产生候选；参考文献零候选。
- 普通词在下一文件精确复用且 bge-m3 调用数为零；高风险词仅管理员可终审。

## 阻塞解除记录（2026-09-15）

- Caddy 实际生产配置为 `/home/dev/qyunsgen/config/Caddyfile-production-public`，由容器 `qyunsgen-caddy` 以只读方式挂载；`translate.qyunsgen.com` 仅代理 `/api/v1/*` 到 `127.0.0.1:8010`、`/dl/*` 到 `127.0.0.1:8765`，其余 Gradio 流量到 `127.0.0.1:7860`，没有 `/internal/workbench` 路由。`caddy adapt` 校验通过，内部工作台接口没有被公网代理；侧车仍只监听回环地址。
- 已定位并修复真实登录身份丢失的根因：Gradio 队列回调只对可注入的定位参数传递 `gr.Request`，原补丁把 `request` 放在 `*ui_args` 后，导致回调静默得到空用户名。现已将 `request` 放在 `*ui_args` 前，并增加旧补丁自动迁移及回归测试。
- 真实浏览器证据：`/home/dev/tmp-bridge/qy-plan060-browser-authenticated-term-review.json`。测试账号登录成功，正确上传入口与翻译按钮可见；翻译完成后显示 `专业词汇：待确认 17`，不再显示“请登录后使用专业词库”。
- 真实浏览器面板证据：`/home/dev/tmp-bridge/qy-plan060-browser-term-panel.json`。点击术语徽标后，“保存术语决定”按钮与双语术语面板可见，确认入口已形成；本次样本为 `CM310 Ph 3.pdf`，候选清单为 17 条。
- 两次浏览器验证仅记录到 `upload_progress` 的预期 `ERR_ABORTED` 以及上游远程 PDF worker 加载警告；未观察到术语桥接业务接口错误。该上游预览警告不应冒充为术语闭环通过证据。

本次已解除“真实文献翻译后无候选清单／提示未登录”和“Caddy 配置无法定位”两个阻塞，但 PLAN-060 仍不得整体标记完成；DOCX/PPTX/图片 OCR/表格脚注、参考文献零候选、管理员流程、泰州 LIVE 与真实金标矩阵仍按门禁逐项补证。

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
  - 历史记录曾因未定位实际 Caddy 文件而为 `BLOCKED`；现已确认实际配置路径并通过负向断言。最新门禁应使用 `QYUNSLATION_PLAN060_CADDYFILE=/home/dev/qyunsgen/config/Caddyfile-production-public`。
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

## 追加验证记录（2026-09-15，确认译法字段收口）

- 术语候选表已固定为八列：源词、实际译法、推荐译法、确认译法、风险、类型、次数、状态。
- “实际译法”表示本次文档中可靠对齐到的实际译文证据；“推荐译法”表示 AI 建议；两列由系统回填并只读，缺少可靠来源时显示明确的降级说明，不再显示空白或 `null`。
- “确认译法”是唯一可编辑的沉淀字段，可在表格列内或下方详情框修改；保存时只提交确认译法，不会把证据列误当成人工裁决。
- 打开面板后默认选中第一条候选并回填三类字段；保存成功后重新加载候选列表、显示下一条候选，避免停留在空白确认页。
- 真实浏览器字段验证证据：`/home/dev/tmp-bridge/qy-plan060-browser-confirmed-column.json`；登录、上传、翻译完成、术语面板、三列默认值及确认译法可编辑均已观测。浏览器验证中保留的 PDF worker 远程模块警告属于预览依赖，不影响术语桥接请求。
- 本次只收口确认字段交互；多格式金标、参考文献零候选、表格/脚注完整证据、泰州 LIVE 和四视宽回归仍须按 PLAN-060 门禁补齐，不能据此标记计划整体完成。

## 追加发布记录（2026-09-15）

- 已从提交 `88c951e723deb84095295647dda15cf85616ed5e` 部署生产，执行 `scripts/deploy-translate-stack.sh` 成功。
- `pdf2zh.service` 与 `qyunslation-office.service` 均为 `active`；sidecar 健康检查 HTTP 200，部署前后代码指纹均为 `7542777de0fd`。
- 本地 GUI、`translate.qyunsgen.com` 及生产 API 烟囱检查均返回 HTTP 200；远程 `origin/main` 与本地提交一致。
- 未跟踪的本地 `.cursor/mcp.json` 未参与提交或部署。
