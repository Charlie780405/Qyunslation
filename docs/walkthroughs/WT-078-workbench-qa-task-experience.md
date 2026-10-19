# WT-078：翻译工作台 QA 处理闭环、参数确认与任务管理（收尾）

> 对应计划：[PLAN-078](../plans/PLAN-078-workbench-qa-task-experience/PLAN-078-workbench-qa-task-experience.md)
> 日期：2026-10-19 · 078a–e 已合并部署；078f 已合并（`2dd97d2`）、推送并部署
> 状态：**078f 已部署；浏览器走查和真实文件探测未做**

## 1. 执行摘要

- 078a–e 此前已合并并部署（见各子计划文末记录）；本次完成最后一个子计划 078f（f1–f7），f8 只出评估方案。
- 用户可见的变化：上传前预检会说明文件的限制（加密/损坏/空文件会阻止创建任务，扫描件、宽表格、语言不符等给出提示和建议）；格式与大小上限由服务端下发；任务列表和详情页轮询按状态退避、标签页隐藏即停；操作失败和断网都有页面内反馈；原生 `confirm` 换成可访问的确认框；详情页不再一打开就自动调用外部模型，改为点击“获取推荐译法”，并写明数据是否出内网；同一文件重复预检可复用。
- 未做数据库迁移，未改 078a–e 的语义，未降低任何 QA 阈值，未清理任何数据。

## 2. 变更明细

| 范围 | 文件 |
| --- | --- |
| 后端 | `qyunslation/pipeline/preflight_probe.py`（新）、`qyunslation/api/v1.py`（预检探测、`blocked` 状态、`/settings/schema.upload`、候选列表 `suggester`）、`qyunslation/workbench/term_extract.py`（`term_profile_id_for_run`、`term_suggester_info`）、`pyproject.toml`（pytest 环境关闭探测） |
| 前端新增 | `stores/connection.js`、`lib/{asyncAction,poller,eventTail,fileHash,confirm}.js`、`components/{ConfirmDialog,PreflightIssues}.vue` |
| 前端修改 | `api.js`、`components/{AppShell,TermReviewPanel}.vue`、`pages/{WorkbenchPage,RunDetailPage}.vue`、`next.css` |
| 测试 | 后端 `tests/api/test_plan078f_preflight_probe.py`、`tests/api/test_plan078f_term_egress.py`；前端 `efficiencyLibs`、`workbenchEfficiency`、`runDetailEfficiency`、`apiConnection` 四个新文件，改写 `runBatch`、`runDetailLifecycle`、`workbenchConfirm`、`workbenchUpload` |
| 工具与文档 | `scripts/verify-plan-078.sh`、078f 实施记录、README、总纲 §14、本文 |

构建产物 `qyunslation/static/app` 需在合并前重新构建并单独提交（`build:` 提交，沿用既有做法）。

## 3. 验证结果

| 项 | 结果 |
| --- | --- |
| 078f 新增后端测试 | 22 项全过 |
| 后端全量（`tests`，不含 `tests/structure`） | 最后一次完整运行仅 9 个失败，均为已记录的基线失败；之后仅改了一处 `asyncio.to_thread`，新测试重跑通过，全量未再跑 |
| 前端 `vitest run src/next` | 17 个文件、200 项全过 |
| `npm run build` | 通过（在 078f 代码完成后跑过；之后未改前端） |
| `scripts/verify-plan-078.sh` | 见 §6 |

## 4. 回归与影响

- 前端依赖新后端的 `/settings/schema.upload` 与候选列表 `suggester`，缺失时回退，不报错。
- 预检探测在每次预检（含分片上传完成）时运行，每个文件最多 4 秒；有阻断项时预检为 `blocked`，不能创建任务。关闭方法：`QYUNSLATION_PREFLIGHT_PROBE=0` 并重启。
- 测试夹具上传的是占位字节，因此 pytest 默认关闭探测，探测自己的测试显式开启。

## 5. 已知限制与遗留缺口

- 未做：三浏览器拖放走查（H12）、网络面板请求数实测、真实 PDF/Office 文件的探测准确度与大文件耗时、f8 截图对比、`capabilities` 展示。
- 评估中的方案 A（平台主机上隐藏应用顶栏的重复用户入口）留作下期。
- 完整清单见总纲 §14。

## 6. 上线记录与上线后待办

已完成：合并 `2dd97d2`、推送 main、`deploy-translate-stack.sh`（迁移对齐、前端构建新鲜、sidecar 指纹一致、路由注册均通过），服务重启后 active，8010 端口页面引用新资源，`/api/v1/settings/schema` 未登录 401，日志无错误。详见 078f 文末上线记录。

仍待做：
1. 用一份加密 PDF、一份扫描 PDF、一份宽表格 docx 走预检卡；对比空闲标签页 10 分钟的请求数。
2. 在 Chrome、Firefox、Safari 各做一次拖放走查。
3. 确认 `pdf2zh.service` 单元文件改动（systemd 提示需要 `daemon-reload`，非本次引入）。
