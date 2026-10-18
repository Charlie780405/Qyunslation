# PLAN-078a：状态一致与 QA 诊断基线（P0）

> 状态：未实施 · 依赖：无 · 工作量：6–8.5 人日（含 D1 的 a8）· 对应问题：Q1–Q3、Q6、Q8、Q12、Q13、T5、O4（部分）、O10（部分）

## 目标

先让任务状态可信，再谈处理流程。执行结束的任务不再显示为“翻译中”，也不会被心跳机制改成“已中断”。QA 改为后台执行，只执行一次。服务不可用与质量问题分开表达。同时提供一个只读诊断脚本，用生产数据验证 H1–H6、H11、H13。

## 任务

### a1 复现测试先行（红灯）

- **内容**：先把 H1–H6 写成失败用例，再修代码；修正 `test_plan071e_real_qa_gate` 的替身漂移，改为替换 `get_profile_provider`，或注入 `resolve_term_provider`。
- **文件**：`tests/api/test_plan071e_real_qa_gate.py`、新增 `tests/api/test_plan078a_state_consistency.py`
- **验收**：H3/H4/H5 的用例在当前 `main` 上为红；修复后转绿；`tests/api` 全绿。
- **工作量**：1 人日

### a2 新增 `gated` 状态（执行已结束、待质量处理或复核）

- **内容**：
  - 执行器到达 `layout_complete`/`download_ready` 后写入 `status=gated`（`v1.py:1495-1513`、`:1578-1588`）。
  - `reconcile_stale_runs` 和心跳判定跳过 `gated`（`v1.py:462-500`、`:1563-1573`）。
  - `_RUN_TERMINAL` 改名为“已结束执行”集合，并加入 `gated`，用于归档；删除改由 078e 接管。
  - Office 产物路径在 `gated` 时写入运行目录的状态文件，使重启后批准仍能物化（H2）。
- **迁移** `078a0001`：回填 `status='translating' AND quality_state IN ('qa_blocked','review_ready','qa_degraded') → gated`。对 `interrupted AND quality_state IN (…) AND 存在本代 qa_item` 的行只出报告（脚本 `--apply` 需人工确认），不自动改写。
- **文件**：`qyunslation/api/v1.py`、`qyunslation/workbench/heartbeat.py`、`alembic/versions/078a0001_*.py`
- **验收**：A10；QA 阻断任务可以归档；列表不再轮询它。
- **兼容/回滚**：`down` 把 `gated` 映射回 `translating`。旧前端把 `gated` 显示为“待处理”（`statusLabel` 的默认分支），不会崩溃。
- **工作量**：1.5 人日

### a3 “请求修改”改为显式状态

- **内容**：`request_changes` → `status=gated, quality_state=changes_requested`，不再伪装为 `translating`；`next_action=create_revision`。
- **文件**：`v1.py:2815-2818` 附近及对应测试
- **验收**：H3 转绿；任务显示“已退回修改”，并提供“生成修订版”入口。
- **工作量**：0.5 人日

### a4 QA 移出 GET：后台检查轮次（最小版）

- **内容**：
  - 新表 `qa_check_round`：`id, run_id, generation, round_no, status(pending|running|succeeded|unavailable|failed), rule_set_version, artifact_digest, triggered_by, started_at, finished_at, error_code`。
  - 加唯一约束 `(run_id, generation, round_no)`，并保证每个 `run_id, generation` 最多一条运行中的轮次（PG 用部分唯一索引，SQLite 用应用层锁）。
  - `_refresh` 只负责登记 pending 轮次；由后台循环执行 `_maybe_run_auto_qa` 的逻辑。后台循环复用 `app.py` 启动的 reconcile 循环，或 runner 的 watcher。
  - GET 不再调用 LLM。
- **文件**：新增 `qyunslation/pipeline/qa/rounds.py`，修改 `v1.py`、`qyunslation/app.py`，新增迁移
- **验收**：H6 转绿：两个会话并发 GET 只生成一个轮次和一套 QA 行；列表 P95 延迟不受 QA 影响（用本地 250 条任务压测记录）。
- **兼容**：旧 `qa_item` 行保持不变，078b 再回填轮次。
- **工作量**：1.5–2 人日

### a5 区分“检查未完成”与质量阻断

- **内容**：新增质量状态 `qa_unavailable`。C3 类代码（`TERM_EXTRACTION_DEGRADED`、`AD_QA_SOURCE_UNAVAILABLE`、`QA_INPUT_UNAVAILABLE`）不再计入 blocker，单独计入 `qa_summary.unavailable`；`_formal_gate` 保留 `qa_unavailable` 原因，仍然阻止批准。机密资料按 D1 改用泰州内网术语模型（a8），不提供人工绕过。
- **文件**：`qyunslation/pipeline/qa/engine.py`、`v1.py`（`_maybe_run_auto_qa`、`_formal_gate`）
- **验收**：A3；H1 用例中的界面文案为“质量检查未完成”。
- **工作量**：1 人日

### a6 服务端投影 `lifecycle / allowed_actions / next_action`

- **内容**：在 `_translation_run_dict` 中按主计划 §5.1/§5.2 计算这三个字段。前端 `WorkbenchPage`、`RunDetailPage` 删除本地的状态集合（`WorkbenchPage.vue:197-198`），按钮显隐全部改读 `allowed_actions`。“当前任务”用路由或本地状态保存的 run id 显式绑定，时间线取同一任务同一代（Q13）。删除写死的“尚未开始”“工作区服务正常”（Q12）。详情页状态改用中文映射（Q9 的状态部分）。
- **文件**：`v1.py`、`frontend/src/next/pages/*.vue`、新增 `frontend/src/next/labels.js`、`components/AppShell.vue`
- **验收**：中断任务可以归档（T5）；没有任何地方直接显示英文状态码；vitest 覆盖各 lifecycle 下的按钮集合。
- **工作量**：1 人日

### a7 只读诊断脚本

- **内容**：新增 `scripts/plan078-qa-diagnose.py`。在只读事务中按 `code × format × direction × domain × model × classification × rule_version` 聚合近 N 天数据，输出阻断率、`interrupted` 率、处理时长和无定位占比；不输出文件名或正文；参照 `plan072-gc-orphans.py` 的数据库连接方式。
- **验收**：在本机库上的输出与主计划 §2.1 一致；由用户在生产实例上运行（H11/H13），结果写入 WT-078。
- **工作量**：0.5 人日

### a8 泰州内网术语抽取档案（D1）

- **背景**【码】：翻译档案 `internal-qwen-quality` 已指向泰州 `qwen3.6:35b-a3b`（`model_profiles.py:24-32`，`base_url` 来自 `QYUNSLATION_BASE_URL`），但术语抽取档案只有 `term-deepseek-flash`。`validate_selection` 对机密资料会拒绝任何术语模型（`model_profiles.py:107-108`）；`resolve_term_provider` 对机密资料直接返回 None（`term_extract.py:366-371`）。所以机密任务一定出现 `TERM_EXTRACTION_DEGRADED`（H1）。
- **内容**：
  - 新增 `term-internal-qwen`：`role=term_suggester`、`provider=ollama`，模型 ID 优先读 `QYUNSLATION_TERM_MODEL_ID`，默认与翻译同为 `qwen3.6:35b-a3b`；`egress_scope=none`，在三种资料等级的 `allowed_profiles` 中都可用。
  - `validate_selection`：机密资料只拒绝**外发**的术语模型，不再拒绝所有术语模型。
  - `resolve_term_provider`：显式指定优先；否则按资料等级选择：机密 → `term-internal-qwen`；内部和公开 → 结构化抽取用 `term-internal-qwen`，DeepSeek 只用于补充推荐（`enrich_discovered_suggestions`），并保持现有外发审计。
  - 创建任务时写入快照 `term_model_profile_id`；旧任务快照中没有该字段的，按旧逻辑兼容。
- **风险与验证**：
  1. 结构化 JSON 输出质量。先用 `tests/workbench/test_plan074_term_extract.py` 的样本和 3 份真实文档（一份机密，只在本机处理）离线比较 DeepSeek 与内网 Qwen 的候选召回和 JSON 合法率，结果记入 WT-078；JSON 不合法时沿用现有的 `TermExtractionDegraded`，走 C3 路径。
  2. 泰州 GPU 与翻译共用。术语抽取的并发上限设为 1，并给超时，超时也按 C3 处理，避免拖慢翻译主链路。
  3. 泰州连通性。只读探测健康端点，不在本计划修改泰州部署。
- **文件**：`qyunslation/pipeline/model_profiles.py`、`qyunslation/workbench/term_extract.py`、`qyunslation/gateway/provider.py`（如需新增 ollama 档案的分支）、`tests/api/test_plan071g_model_classification_gate.py`、新增 `tests/workbench/test_plan078a_internal_term_model.py`
- **验收**：H1 用例（机密资料 + 已翻译 PDF + 泰州可用）得到 `review_ready` 或真实术语问题，不再出现 `TERM_EXTRACTION_DEGRADED`；泰州不可用时得到 `qa_unavailable`；机密任务的外发审计为 0 条。
- **兼容/回滚**：新档案是增量。回滚时删除档案注册，机密任务回到原来的“检查未完成”行为（a5 之后不再表现为质量阻断）。
- **工作量**：1–1.5 人日

## 验证

`pytest tests/api tests/workbench`、`vitest run src/next`；新增 `scripts/verify-plan-078.sh`，沿用 PASS/FAIL/BLOCKED 三态，缺少浏览器证据时标 BLOCKED。
