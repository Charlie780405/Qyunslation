# PLAN-078a：状态一致与 QA 诊断基线（P0）

> 状态：**已实现，待合并与部署**（分支 `feat/plan-078a-state-consistency`，2026-10-19；实施记录见文末）· 依赖：无 · 工作量：6–8.5 人日（含 D1 的 a8）· 对应问题：Q1–Q3、Q6、Q8、Q12、Q13、T5、O4（部分）、O10（部分）

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

## 实施记录（2026-10-19）

| 任务 | 状态 | 与计划的差异 / 备注 |
| --- | --- | --- |
| a1 | 完成 | 测试在 `tests/api/test_plan078a_*.py`、`tests/api/_plan078_flow.py`；H1–H6 均有用例。`tests/api/conftest.py` 让 API 测试默认不联网（`pytest-env` 把 `DOCUTRANSLATE_BASE_URL` 指到 openai.com，术语模型默认可用后，未打桩的测试会真的发请求）。 |
| a2 | 完成 | `gated` 状态；迁移 `078a0001` 回填 `translating` 且质量状态在 `qa_blocked/review_ready/qa_degraded` 的行（已被心跳标成 `interrupted` 的不改，只由诊断脚本报告）。Office/图片执行器的输出在进入闸门时复制到运行目录 `executor-outputs/`（含 `manifest.json`，不放进 `settings_snapshot`，避免重试时被带到下一代），服务重启后仍可批准并物化正式产物；续跑时会清除。**取消语义**：对 `gated` 任务 `cancel` 仍然有效，含义改为“放弃本版本”（接口里叫 `discard`，状态变为 `cancelled`，质量状态保留），这样保持了原来的接口契约。 |
| a3 | 完成 | “请求修改”→ `gated` + `changes_requested`；下一步是生成修订版（修订版流程在 078b b6，目前用“重试”）。 |
| a4 | 完成（含一处补充） | 迁移 `078a0002` 新增 `qa_check_round`（每个任务代最多一个活跃轮次的部分唯一索引 + 租约）；GET 只登记轮次，检查在 `qa-round` 线程池里用独立 Session 执行，**提交后**才派发。`QYUNSLATION_QA_MODE=inline` 用于测试和脚本，默认 `background`；相关环境变量：`QYUNSLATION_QA_WORKERS`（默认 2）、`QYUNSLATION_QA_PENDING_LEASE_SEC`（120）、`QYUNSLATION_QA_LEASE_SEC`（600）。派发丢失或进程重启后，租约到期会由下一次读取接管。检查崩溃会落成 `QA_ROUND_FAILED`（检查未完成），不会一直“检查中”。过期结果不落地：任务已放弃、重试或删除时，轮次记为 `superseded`。**补充**：检查进行中正式门禁拒绝批准（`qa_checking`）；复检在已有轮次时是幂等的。历史 `qa_item` 暂未回填成“第 0 轮”，留给 078b b2。 |
| a5 | 完成（范围收窄） | 严重度新增 `unavailable`，`TERM_EXTRACTION_DEGRADED`、`AD_QA_SOURCE_UNAVAILABLE` 改用它；质量状态 `qa_unavailable`；阻断问题优先于“未完成”。`QA_INPUT_UNAVAILABLE`（读不了 PDF）仍是 warning，改成 `unavailable` 会让这类任务从“可复核”变成“不可批准”，属于行为变化，留到 078b 与规则注册表一起决定。 |
| a6 | 完成（后端全部、前端主要部分） | 服务端新增 `lifecycle / allowed_actions / next_action / pending_counts / qa_check`；前端 `labels.js` 统一中文文案，列表和详情页按 `allowed_actions` 显隐按钮；活跃任务以 `lifecycle` 判断，阻断任务不再占用实时进度；侧栏时间线标明所属任务（Q13）；去掉写死的“尚未开始”“工作区服务正常”；详情页动作都有进行中/成功/失败反馈，`?tab=qa` 自动选中第一个阻断项；翻译模型下拉只列翻译档案。未做：详情页轮询在非执行状态下仍每 3 秒一次（078f f3）。 |
| a7 | 完成 | `scripts/plan078-qa-diagnose.py`（只读会话，不输出文件名和证据正文）。**尚未在生产库上运行**：需要生产库连接串，本环境按规定不读取 `.env`，请在有权限的环境执行 `QYUNSLATION_DATABASE_URL=... python3 scripts/plan078-qa-diagnose.py --days 30`，结果用于验证 H11、H13。 |
| a8 | 完成（默认规则有调整） | 新增 `term-internal-qwen`（不外发，机密资料只能用它）。默认术语模型：机密→内网 Qwen；其他等级**保持原行为**（配置了 DeepSeek 就用它），没有配置时改用内网 Qwen，而不是像以前那样没有术语模型、让每个任务都“术语抽取降级”。这比计划里“所有等级都改用内网”更保守，避免内部/公开资料的术语建议质量在没有对比数据前发生变化；对比评测（3 份真实文档）仍待做。泰州服务的连通性只做了代码层假设，未做实机探测。 |

### 验证结果

- 后端：`tests/api tests/workbench tests/ui tests/persist tests/contracts tests/auth tests/pipeline tests/scripts tests/quality tests/structure` 共 1060 通过，13 个失败里 12 个在未改动的 `main` 上同样失败（7 个 SQLite 迁移往返、`test_plan072_migration`、`test_plan060_evidence`、`test_plan066_next_surface`、3 个 structure 测试），另 1 个是本分支新增迁移测试里写死了链头，已修。
- 前端：`vitest run src/next` 全部通过（含 axe 无障碍检查）。
- PostgreSQL：用一次性临时容器（已删除）跑完整迁移链到 `078a0002`、回滚到 `074a0001` 再升级均通过；8 线程并发登记同一轮次只产生 1 条记录，并发抢占只有 1 个成功。
- 未验证：真实浏览器走查、泰州内网模型的术语抽取质量、生产数据上的诊断结果。

### 部署步骤（需要用户确认窗口，本分支尚未部署）

1. 备份业务库（参照 `docs/runbooks/pg-loopback-binding.md` 的备份方式）。
2. 合并后在主工作区执行 `alembic upgrade head`（`078a0001` 回填状态、`078a0002` 建表）；`scripts/deploy-translate-stack.sh` 的发布前检查会要求迁移已对齐。
3. `bash scripts/deploy-translate-stack.sh` 重启服务；确认没有进行中的任务（重启会打断执行中的翻译）。
4. 上线后在生产库运行诊断脚本，核对“状态不一致”三项是否为 0（已被心跳标成中断的 QA 阻断任务需要人工决定是否续跑）。
5. 回滚：`alembic downgrade 074a0001`（把 `gated` 映回 `translating`、`qa_unavailable` 映回 `qa_blocked`、`unavailable` 严重度映回 `blocker`）并还原上一个发布版本；新增列表字段对旧前端无害。

## 验证

`pytest tests/api tests/workbench`、`vitest run src/next`；新增 `scripts/verify-plan-078.sh`，沿用 PASS/FAIL/BLOCKED 三态，缺少浏览器证据时标 BLOCKED。
