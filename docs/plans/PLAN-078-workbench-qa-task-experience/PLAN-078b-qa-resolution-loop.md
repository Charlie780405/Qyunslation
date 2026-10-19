# PLAN-078b：QA 处理闭环（P0）

> 状态：**已实现，待合并与部署**（分支 `feat/plan-078b-qa-resolution`，2026-10-19；实施记录见文末）· 依赖：078a · 工作量：9–13 人日 · 对应问题：Q4、Q5、Q7、Q9–Q11

## 目标

用户从任何入口一次点击就能进入对应任务、对应版本的未处理问题。每一项都能看懂、能定位（或说明为何无法定位），并有明确可执行的处理路径。复检保留历史并展示差异。“清理 QA”只有四种合法含义：隐藏已处理项（视图筛选）、重新检查（新轮次）、确认误报（第二人确认、留审计）、历史维护（只追加，不删除）。

## 任务

### b1 规则注册表

- **内容**：新增 `qyunslation/pipeline/qa/registry.py`。每个代码登记：中文标题、“为什么影响交付”、建议动作、类别（C1–C4/警告，见主计划 §5.2）、`waivable`、`waiver_roles`、`batchable`、`locatable`（支持的定位粒度）。按注册表内容和规则实现文件计算摘要作为 `rule_set_version`，替代写死的 `"076-qa-v1"`（Q11）。未登记的代码按 C1 处理，标题显示为“未登记检查项（代码）”，并在日志中告警。
- **文件**：`registry.py`、`engine.py`、`pdf_inspect.py`、`ad_qa.py`；接口 `GET /qa-rules`
- **验收**：仓内所有 `code="…"` 都已登记，由一个扫描测试保证；前端不再出现英文 severity/code 作为主文案（Q9）。
- **工作量**：1.5 人日

### b2 数据模型：轮次、位置、处置

- **内容**：
  - `qa_item` 增加 `round_id`、`fingerprint`（代码 + 位置 + 证据规范化哈希）、`location_json`（`page`、`object_id`、`output_kind`、`locatable`、`unlocatable_reason`）、`rule_class`。
  - 新表 `qa_disposition`，只追加：`id, run_id, generation, fingerprint, round_id, action(acknowledge|report_false_positive|confirm_false_positive|reject_false_positive|grant_waiver|revoke_waiver), reason, evidence_json, actor_sub, actor_role, created_at`。
  - 处置绑定 `fingerprint`，复检后同一问题仍存在时处置继续生效；`artifact_digest` 变化（新版本）时处置不继承，界面提示“上一版本曾授权例外”。
- **迁移** `078b0001`：历史 `qa_item` 回填为第 0 轮（legacy）并计算 fingerprint；不删除任何行。
- **工作量**：1.5 人日

### b3 可定位取证

- **内容**：`read_pdf_facts` 保留逐页文本；`check_protected_literals`、`latin_residue_ratio`、`detect_text_artifacts`、`check_author_metadata` 改为逐页输出 `page`。AD 文本路径如果有段落对齐（`translation_trace`）就输出段落锚点，否则 `locatable=false`，`unlocatable_reason="全文统计规则"`。对照视图支持 `?page=&obj=` 跳转（`stores/runDetail.js` 已有）。
- **验收**：主计划 §2.1 中可定位的代码（字面量、残留、乱码、作者、Logo、页数）在新数据中都有 `page`；不可定位的项显示原因。
- **工作量**：2 人日

### b4 统一检查服务（首检 = 复检）

- **内容**：`_maybe_run_auto_qa` 和 `_requalify_translation_run` 合并为 `run_qa_round(run, trigger)`。逻辑包括：
  - 抽取降级时重跑术语抽取；
  - 传入 `semantic_degraded`；
  - 写入 `rule_set_version` 与 `artifact_digest`；
  - 发出阶段事件（“第 N 轮检查：新增 a、已解决 b、仍存在 c”）；
  - 提交时校验 `run.generation`、`artifact_digest` 未变，变了就丢弃结果，防止过期结果覆盖新版本；
  - 只在 `gated` 状态下允许（修复 H5）。
- **接口**：`POST /translation-runs/{id}/qa-checks`，需 `Idempotency-Key`，返回 202 和轮次 ID；同时已有运行中的轮次时返回该轮次。
- **验收**：A2、A3；H4/H5 用例保持绿；连点只产生一个轮次。
- **工作量**：2 人日

### b5 处置接口

- **内容**：`POST /translation-runs/{id}/qa-items/{item_id}/dispositions`，请求体 `{action, reason, expected_round_id}`。
  - 服务端按注册表和 §5.2 矩阵校验角色和类别。按 D3，C2/C4 授权例外允许提交人本人在具有 R/A 角色时操作，并记录 `self_review=true`。C1 只允许 `report/confirm/reject_false_positive`，其中 confirm 必须由反馈人以外的 T/A 完成（这是规则判定，不受 D3 影响）。`reason` 至少 10 个字符。
  - `expected_round_id` 过期返回 409。
  - 批量接口 `POST …/qa-dispositions:batch` 只接受同一代码、`batchable=true`、显式列出的 ID，逐项返回结果；默认不选中任何阻断项。
  - 每次处置后重算 `quality_state` 和 `formal_gate`，不需要重跑检查。
- **验收**：A4；越权、C1 例外、C1 由反馈人本人确认都被拒绝；自审被允许，但带 `self_review` 标记；审计日志完整。`LITERAL_MISSING_DOSE/FREQ` 不能批量确认（D2 评估期）。
- **工作量**：1.5 人日

### b6 修复路径：生成修订版

- **内容**：复用 `retry` 和 `apply-corrections` 的新代机制，合并为 `POST /translation-runs/{id}/revisions`。入参为 078c 的确认配置，外加当前术语裁决与单位译名修订。旧版本冻结，`superseded_by` 指向新版本；新版本执行完成后自动做首轮检查，界面显示与上一版本的问题差异。确认抽屉中明确提示“将重新翻译全文，预计耗时与上次相近”，只引用已知的历史耗时。
- **依赖**：078c（确认抽屉）。在 078c 之前可以先用预填旧快照的只读确认。
- **工作量**：1 人日

### b7 前端：QA 待办面板与统一入口

- **内容**：
  - 新增 `components/QaTodoPanel.vue`，替换 `ObjectInspector` 中的列表部分，对象详情保留；
  - 支持路由 `/workbench/:runId?tab=qa&item=`；
  - 入口：工作台待办条、“当前任务”卡、列表行的“处理质量问题（N）”、详情页首屏；
  - 交付清单汇总 QA 阻断、C3 未完成、待审术语、单位译名、版本是否最新、正式稿是否已解锁；
  - 下一步卡片取自服务端 `next_action`；
  - 复检和处置都有进行中、成功、失败三种状态，并可再次操作；
  - 审阅稿和草稿预览加“非正式”标识。
- **验收**：A1、A4；axe 无 serious/critical 问题；键盘可以完成选择问题 → 定位 → 处置。
- **工作量**：2–3 人日

### b8 正式门禁口径统一

- **内容**：`_formal_gate` 只统计“当前代 + 最新已完成轮次”中未处置的阻断项（已授权例外的 C2/C4 视为已处理，C1 只有确认误报才视为已处理）；术语按代过滤（Q10）；`qa_unavailable` 阻止批准。下载正式稿与批准使用同一函数。
- **验收**：A2、A4；列表计数、详情计数、门禁三者来自同一函数，由测试断言。
- **工作量**：0.5 人日

### b9 规则校准（与开发并行，需人工）

- **内容**：执行 H7、H8、H9。对确认的误报修规则并补单测，规则集版本随之变化，再对受影响任务复检。产出每个代码的阻断率和确认误报率基线，作为后续指标。
- **D2 专项**：对 `LITERAL_MISSING_DOSE/FREQ` 在 gold 语料和近 30 天任务（只读）上回放，人工标注每条命中的真伪（真实缺失、格式差异、单位本地化、提取断行），产出误报率和典型误报模式，写入 `docs/assessments/plan078-dose-freq-false-positive.md`，交给用户决定是否升为 C1。报告提交前不改这两条规则的严重度。
- **验收**：每条规则的改动都有样本证据，不整体调低阈值；D2 报告附样本数和标注口径。

## 实施记录（2026-10-19）

| 任务 | 状态 | 与计划的差异 / 备注 |
| --- | --- | --- |
| b1 规则注册表 | 完成 | `pipeline/qa/registry.py`：35 个检查代码的中文标题/影响/处理建议、类别 C1–C4/W/I、可批量性、指纹字段、规则集版本（对注册表和规则实现文件内容取摘要，替代写死的 `076-qa-v1`）。扫描测试用 AST 保证仓内所有 `QaFinding`/`_finding` 代码都已登记；未登记代码按 C1 处理。`GET /qa-rules`。 |
| b2 数据模型 | 完成（不回填） | 迁移 `078b0001`：`qa_item` 增加 `round_id/fingerprint/location_json/rule_class/is_current`，`qa_check_round` 增加 `rule_set_version/artifact_digest/diff_json`，新表 `qa_disposition`（只追加）。**历史条目不回填成“第 0 轮”**：老条目默认仍是当前结论，读取时按需计算指纹和类别，第一次被处置时才落库——避免在生产库上逐行改写。 |
| b3 可定位取证 | 完成 | 新增 `pipeline/qa/locate.py`。PDF：保护性字面量（原文页码+摘录）、作者信息、英文残留/未翻译（译文页码+残留行）、乱码/标记残留、序数伪影、回退段落、首页图片；AD：数字漂移引用丢失数字所在的原文段落（有页文本给页码），否定/情态引用原文句子，术语缺失/禁用引用位置。无法定位的写明原因（注册表给出）。 |
| b4 统一检查 | 大部分在 078a 完成，本次补齐 | 复检不再删除旧条目，保留历史并计算新增/已解决/仍存在；检查期间产物变化则丢弃结果（`output_changed`）；轮次记录规则集版本与产物摘要。接口沿用 `POST /requalify`（幂等），没有新增 `/qa-checks`。 |
| b5 处置接口 | 完成 | 单条 `POST …/qa-items/{id}/dispositions` 与批量 `POST …/qa-dispositions/batch`。规则：C1 只能反馈误报，确认/驳回由术语管理员或管理员完成且必须是反馈人以外的人；C2/C4 由复核人（含提交人本人自审，标记 `self_review`）写明理由后授权例外，可撤销；C3 无处置；警告可确认已阅；理由至少 10 个字；过期轮次/旧条目 409；相同决定重复提交是空操作；批量只限同一代码、`batchable`，剂量/频次不可批量；每次处置写审计。 |
| b6 修订版 | 完成（不含参数确认抽屉） | `POST …/revisions`（可选带入已确认的单位译名更正）；retry/apply-corrections 与其共用 `_spawn_next_generation`；旧版本冻结并返回 `superseded_by`；新版本首轮检查与上一版本对比；上一版本的例外不继承但会提示。**预检续期**：任务仍在使用的原文件不受 24 小时窗口限制，重试/续跑/修订时自动续期；原文件已被清理时返回明确的 `SOURCE_UNAVAILABLE`（这是 078c c5 的一部分，提前完成）。参数确认抽屉仍在 078c。 |
| b7 前端 | 完成 | `QaTodoPanel`（下一步、交付清单、筛选、问题卡、位置+摘录+在对照视图定位、逐项处置表单、批量处理、生成修订版、上一版本例外提示）；`?tab=qa&item=` 直达；工作台首页待办条；非正式预览标注。 |
| b8 门禁统一 | 完成 | `qa_summary.open_blocker`（处置后仍未处理的阻断数）由检查和每次处置后重算并持久化，`_formal_gate`、列表计数、详情计数同源；处置后质量状态自动在 `qa_blocked`/`review_ready` 间切换。术语门禁仍不按代过滤（Q10 的另一半留给后续）。 |
| b9 规则校准 | 完成工具与 D2 评估；H7/H8/H9 的人工部分未做 | `scripts/plan078-qa-replay.py` + `docs/assessments/plan078-dose-freq-false-positive.md`。**D2 结论：暂不升级**。受控探针显示剂量/频次检查对“正确但写法不同”的译文误报 12/15，已让规则认可等价写法（毫克/微克/毫升/每2周/每日两次…），降到 1/15，真实缺陷 6/6 仍报。AD 数字规则在 24 组语料上 0 命中、对照实验召回 24/24，因此生产里 5 个 `AD_NUMBER_DRIFT` 不是规则对普通写法过于敏感，需要人看原文（H9）。 |

### 验证结果

- 后端：`tests/api tests/pipeline tests/scripts tests/workbench tests/ui tests/persist` 545 通过，9 个失败与未改动的 `main` 完全一致（7 个 SQLite 迁移往返、`test_plan060_evidence`、`test_plan066_next_surface`）。
- 前端：`vitest run` 84/84，含无障碍检查；`npm run build` 通过。
- PostgreSQL：用一次性临时容器（已删除）跑完整迁移链到 `078b0001`、回滚到 `078a0002` 再升级均通过，并做了新列/新表的 ORM 往返。
- 未验证：真实浏览器走查；真实临床/申报文档上的误报率；生产里 5 个 `AD_NUMBER_DRIFT` 的真伪。

### 部署注意

1. 需要 `alembic upgrade head`（`078b0001`，仅新增列/表），再用 `scripts/deploy-translate-stack.sh` 重启。
2. 回滚：`alembic downgrade 078a0002`。**这是唯一不可逆的一步**——会删除 `qa_disposition` 表（审计记录）。如果上线后已有处置记录，回滚前先备份该表。
3. 新字段对旧前端无害；旧前端看不到处置入口。

## 不做

不提供段落级原位编辑（后续增强）；不在本子计划删除任何历史 `qa_item`；不新增外部模型调用。
