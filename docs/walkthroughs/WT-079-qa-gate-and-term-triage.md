# WT-079：QA 阻断分级、术语审核准入、对照视图定位与上线收口（实施走查）

> 日期：2026-10-19 · 计划：[PLAN-079](../plans/PLAN-079-qa-gate-and-term-triage/PLAN-079-qa-gate-and-term-triage.md) v3 · 分支：`docs/plan-079-qa-gate-triage`（本记录对应的改动**未提交、未合并、未部署**）

## 1. 本轮做了什么

按 PLAN-079 §11 的顺序，先做了无需用户确认的项，再做依赖它们的 C、D。门禁开关默认 `legacy`，门禁口径本身不因部署而改变。但 legacy 并不等于“完全无行为变化”，以下几项在默认配置下就会生效（见 §10）：预检复用的语言提示、乱码判定的正则收紧、docx/pptx 工作流的修复、工作台的加载失败提示。上线前需要用户确认的事项见 §6。

| 编号 | 状态 | 说明 |
| --- | --- | --- |
| A 对照视图定位 | 已实现，**Chromium + WebKit 三种宽度实测通过**（用拦截接口的本地构建，未登录真实环境） | `DualCanvasViewer.focusAnchor`：目标侧切换、同页重复点击也执行、滚入视口并短暂高亮、`aria-live` 播报、越界/未加载给出原因、加载中暂存锚点。`RunDetailPage.locateAnchor` 改为调用它；浏览器实测另发现并修复 `PdfPane` 的页偏移缺陷（见 §5） |
| B 只读基线 | 已实现并在本机库跑过一次 | `scripts/qa/plan079_baseline.py`，结果见 §3 |
| C 术语与门禁解耦 | 已实现，**默认 `legacy`** | `QYUNSLATION_TERM_GATE_MODE=legacy/shadow/enforce`、`TERM_REVIEW_REQUIRED`、`violation`→阻断型 `TERM_TARGET_MISSING`、`phrase_denylist`（规则版本 `079-v1`）、前端文案 |
| D 乱码证据与分级 | 已实现；**源文继承降级默认 auto（仅限未映射字形标记，见 PLAN 乱码修复）** | 检测器与码点写入证据。源文同页也有的字符降为警告 `TEXT_ENCODING_INHERITED`，默认 `auto` 仅对 C0/U+FFFD 这类未映射字形标记生效（译文标记数不得超过源文，双语 PDF 允许 2 倍）；`1` 为旧的整族重叠降级；`0` 关闭。收紧 `Ã`/`Â` 判定，葡/西语大写名不再命中（这一条默认生效） |
| E 回归、影子灰度、切换 | **未做**（E1 已做，E2/E3 需要部署与一周观察） | 见 §6 |
| F2 预检误阻断 | 已评估 | §4 |
| F5 测试基线 | 已清零 | §5 |
| F8 浏览器实测 | Chromium + WebKit 已做，Firefox 未做 | §6：拖放四种情形与轮询请求数，18/18 |
| F7 排序规则告警 | 只读检查已做，**未写库** | §8：影响清单；REINDEX 与刷新版本待批准（D6） |
| F10 文档状态 | 已修正 | 索引、PLAN-077 README/正文、WT-077 T3、WT-078 §7 标题 |
| F12 复用预检的语言提示 | 已做；`capabilities` 字段**没改** | 复用预检时按新选的源语言只重算 `LANGUAGE_MISMATCH`（其余问题保持）；`capabilities` 在仓库内无人读取，但删除或改值是接口契约变更，等你确认外部调用方后再动 |
| F14 静默 `catch {}` | 已处理 | §5 |

## 2. 设计要点与取舍

- **门禁只读 QA 条目。** `enforce` 下 `unresolved_terms` 不再进入 `reasons`，但 `unresolved_term_count` 仍在响应里（供展示）。`legacy` 和 `shadow` 的判定与以前完全一致。
- **`shadow` 不改变任何结论。** 它只在 QA 轮次里把“旧口径的术语原因（`unresolved_terms`）/ 新口径的术语原因（`TERM_REVIEW_REQUIRED` 与 `violation` 补发造成的阻断）/ 各自条数”写进 `run.term_summary.gate_shadow`，并打日志 `plan079.gate_shadow`（不含术语原文）。shadow 评估自身出错只记日志，不会让健康的 QA 轮次失败；`enforce` 则保守：出错让轮次进入“检查未完成”，绝不悄悄放行。
  - **端到端测试暴露的设计修正：** 最初记录的是“完整门禁原因”，但轮次进行到一半时任务还是 `draft`（会混进瞬时的 `qa_checking`），`qa_summary` 也还是上一轮的，记录会失真。现在只记“由术语策略引起”的部分，门禁的其余部分在两种口径下相同，由 `plan079_baseline.py` 按实时状态另行统计。
- **`TERM_REVIEW_REQUIRED` 只用能确定性计算的信号。**
  - a `multi_target`：同一 `source_norm` 在本文有 ≥2 种真正不同的译法（“自闭症”与“自闭症（ASD）”算一种）；
  - c `alias_conflict`：术语库对同一原文给出两个不同的批准译名（且在本文出现过）；
  - b（源文出现但译文既无译名也无原文）**没有上线**：现有对齐是模型段落对齐（`workbench/term_align.py`），不能作为门禁输入，这就是 PLAN-079 假设 H4 的结论。
  - 必要条件：术语类型属于药名/生物制品/靶点/疾病/安全性事件/终点/量表/方案；已被术语库解决的和已裁决的不算；每文档最多 5 条，其余只计数。
- **发现并补上一个会被悄悄放行的缺口（H3 的反面）。** `term_snapshot` 对**非高风险**硬约束术语缺失只发**警告**级 `TERM_TARGET_MISSING`（高风险才是阻断），而 `violation` 候选是**段落级**信号（该段源文有术语、对齐译文没有批准译名）。以前它们靠“未决候选”阻断交付；`enforce` 后如果不处理就会放行。所以 `violation` 现在会补发一条阻断型 `TERM_TARGET_MISSING`（同一概念已有阻断条目时不重复）。
- **门禁租户白名单没做。** D4 已定“全租户影子”，`QYUNSLATION_TERM_GATE_TENANTS` 是计划里的可选项，需要时再加。
- **A4（“返回问题”按钮）没做**，它在计划里是可选项。

## 3. 阶段 B 基线（本机库，只读，聚合）

运行：`scripts/qa/plan079_baseline.py`（只做 SELECT；输出写入 `var/plan079/`，不入库）。

| 项 | 结果 |
| --- | --- |
| 已到达门禁的任务 | **1 个**（样本极少，不能据此校准） |
| 门禁原因 | `qa_blockers` 1、`unresolved_terms` 1；**只因术语被阻断的任务：0** |
| 未决候选 | 123 条：高风险 8 条；模型抽取 52、确定性 71；其中 `量表/终点/方法` 类 14 条 |
| `TEXT_ENCODING_ARTIFACT` | 2 个条目、10 个锚点，摘录里的码点族**全部是 C0 控制字符**（没有 U+FFFD、C1、mojibake） |
| `violation` 候选 | 0 条，无法对账 |

对假设的结论（按计划，样本不足记为“未知”，**不据此改任何生产阈值**）：

- H1（多数乱码命中来自控制字符）：本机样本**支持**，但只有 1 个任务；是否来自源文，需要源文页文本比对，现已由 D 在运行时完成（同页同族→降级）。
- H2（只因术语被阻断的任务占多数）：**未知**，样本里是 0/1。需要生产多任务的 `shadow` 数据。
- H3（每个 `violation` 都有对应 C4 条目）：**无数据**；但代码层面已确认 `violation` 与文档级检查口径不同，所以 C 补发了阻断条目（见 §2）。
- H4：见 §2，b 不可用，a、c 可用。
- H5（渲染前译文字符串可取回）：**未验证**。因此 D 没有做“渲染前不存在→抽取伪影降级”这一条，只做了“源文同页继承”和“大写人名不计”。
- B2（人工标注 ≥30 条乱码、≥100 条候选）：**未做**，需要人工。

## 4. F2：预检探测误阻断评估

脚本：`scripts/qa/plan079_probe_eval.py`（只读）。对本机已有的 129 份**能正常使用的文件**运行探测：

| 来源 | 文件数 | 阻断 | 警告 | 探测失败 | 最长耗时 |
| --- | --- | --- | --- | --- | --- |
| `var/preflights`（已上传过） | 35（docx 32、pdf 2、txt 1） | 0 | 0 | 0 | 0.82 s |
| `var/translation-runs` | 38（txt 27、pdf 11） | 0 | 0 | 0 | 2.54 s |
| `deliverables` | 53（png 29、pdf 24） | 0 | 0 | 0 | 0.56 s |
| `docs/gold` | 3（md） | 0 | 0 | 0 | 0 s |

结论：**没有发现误阻断**，耗时都在 4 秒上限内。局限：本机没有真实的加密、损坏、扫描、宽表格、pptx 样本，所以**真阳性一侧没有验证**，仍只靠合成夹具；`PROBE` 逃生开关 `QYUNSLATION_PREFLIGHT_PROBE=0` 保留。

## 5. 测试基线与顺带修复

全量后端测试（不含 `tests/structure`）之前有 9 个已知失败，现已全部处理：

- 7 个 SQLite 迁移往返：`073a0001`、`074a0001` 在 SQLite 上执行了不支持的约束 ALTER。改为 SQLite 走 `batch_alter_table`，**PostgreSQL 路径原样不变**（已部署的迁移没有改动其 PG 行为）。
- `test_plan060_evidence`：这是**真实缺陷**，不只是测试问题。`BaseWorkflowParams` 的 `domain_profile`、`document_profile` 被 `model_dump` 后传给翻译器配置，而所有翻译器 dataclass 都不接受它们，docx/pptx 经 `create_workflow_from_payload` 时抛 `TypeError`。已在 `qyunslation/core/factory.py` 中排除这两个字段（提示词编译发生在更早的位置）。线上 docx 任务是否走这条路径未核实。
- **`PdfPane` 页偏移缺陷（真实浏览器才暴露，jsdom 看不到）：** `pageTop` 用 `offsetTop`，而滚动容器不是定位祖先，`offsetTop` 相对页面主体而不是滚动容器，查看器在页面越靠下偏差越大（实测目标页被滚过头约 1500 像素）。这意味着此前“跳页”在文档较长时本来就落不到正确的位置。已改为用几何位置相对滚动容器计算，`detectPage` 同步受益；jsdom 没有布局时回退 `offsetTop`。
- **隐藏页签的画布在激活后才测宽：** 平板/手机上切到目标侧后页高会变，之前算好的滚动位置作废。`PdfPane` 现在记住最近一次定位请求，激活并重新测量后再对准一次。
- `test_plan066_next_surface`：断言仍指向旧版 `WorkbenchPage`，改为指向 078c 之后的实际位置。
- 前端 `runDetailPage.test.js`：mock 引用已删除的接口，9 个用例在干净工作树上就已失败（此前记录的 205/205 与现状不符）。

F14：`TermbasePage` 的加载失败现在显示可重试的提示；`stores/workbench.js` 在网络中断时不再丢弃“未完成上传”的指针（只有服务端明确答复才清除）；`SettingsPage` 的管理员提示改为说明性注释；`logout.js` 本来就有说明，保持不变。

## 6. 验证与尚未做的事

验证：

- 前端 vitest **216 项全绿**（新增 `dualCanvasViewer.locate.test.js` 6 项、`silentCatch.test.js` 3 项，并扩展 `qaTodoPanel.test.js`）；`vite build` 在临时目录通过（**没有**覆盖已跟踪的 `qyunslation/static/app`）。
- **真实浏览器：** `scripts/browser/plan079-locate-check.mjs`（Playwright，Chromium + WebKit × 桌面 1440、平板 800、手机 390 × 译文 5 页/3 页）**70/70 通过**：查看器滚入视口；目标侧目标页位于其画布顶部；目标页被高亮；播报“已定位到源文第 N 页”；同页再次点击（先把页面滚走）仍有响应；锚点在译文侧时平板/手机自动切到译文页签、另一侧隐藏；页码越界给出“超出源文页数（99 > 5）”“超出译文页数（4 > 3）”；无页面级报错。接口、会话和 PDF 都是拦截并伪造的，**没有访问任何真实服务**。WebKit 用的是缓存里与 Playwright 版本不完全匹配的构建（`QY_WEBKIT_EXEC`）。
- **F8（`scripts/browser/plan079-workbench-check.mjs`，Chromium + WebKit，18/18）：** 拖放进入时高亮；支持的文件被选中；不支持的格式和超过上限的文件被拒绝并说明原因；落在拖放区之外的文件不会让标签页跳走；空闲列表用假时钟快进 10 分钟，API 请求 **0** 次；有任务执行且无变化时快进 1 分钟，列表请求 **8** 次（固定 2 秒定时器会是 30 次；脚本带“确实在轮询”的下限对照，避免假通过）。
- 后端新增 `tests/api/test_plan079_baseline.py`（5）、`tests/api/test_plan079_term_gate.py`（17）、`tests/api/test_plan079_gate_e2e.py`（3，真实 QA 轮次下三种开关）、`tests/api/test_plan079_language_reuse.py`（4）、`tests/pipeline/test_plan079_encoding.py`（16）；全量结果见本文末尾的“最终回归”。

**没有做，也不能由我单方面做：**

1. **登录后的真实页面走查（F1）与键盘/读屏**：A 的浏览器检查用的是伪造接口；真实账号下的页面、焦点移动的读屏体验、触屏实机都没有验证。
2. **部署与上线**：需要重新 `vite build` 并提交 `static/app`、合并、运行 `scripts/deploy-translate-stack.sh`。这些是对外动作，等你确认。
3. **E2/E3 影子灰度**：部署时设 `QYUNSLATION_TERM_GATE_MODE=shadow`，观察一个工作周，逐个抽查“新口径放行、旧口径阻断”的任务，再决定是否 `enforce`。差异报告用 `scripts/qa/plan079_shadow_report.py`（只读；数据源是 `run.term_summary.gate_shadow` 和 `plan079.gate_shadow` 日志）。总门禁脚本是 `scripts/verify-plan-079.sh`。
4. **B2 人工标注**与 H2、H3、H5 的最终结论。
5. F0、F1、F3、F4、F6、F7、F8、F9、F11、F12、F13、F15–F17：需要用户确认、账号、窗口或权限，见 PLAN-079 §11。
6. `pdf2zh.service` 单元状态仍无法在本会话核实。
7. F8 的 Firefox 与触屏实机未做（本机 Playwright 缓存里没有 Firefox）。

回滚：把 `QYUNSLATION_TERM_GATE_MODE` 改回 `legacy` 并重启即可；乱码证据字段和 `TEXT_ENCODING_INHERITED` 只增不改，旧客户端忽略即可。

## 7. 最终回归

- 后端全量（不含 `tests/structure`）：**987 passed，0 失败**；此前 9 个基线失败已清零。
- `tests/structure`：641 passed、6 skipped、**3 failed**。这 3 个在干净工作树上同样失败，与本计划无关，**未处理**：`test_manifest_contract.py::test_committed_json_schema_matches_model`、`test_manifest_store.py::test_schema_major_mismatch_is_treated_as_miss`、`test_plan059_fidelity.py::test_ljae_semantic_counts_are_not_physical_image_counts`（manifest 的 schema 契约与版本，属于更早的计划）。改 `text_sanitize` 相关的 `test_plan045_sanitize.py` 在其中，通过。
- 前端 vitest：**216 passed**（20 个文件）。
- 真实浏览器：A 的定位 70/70，F8 的拖放与轮询 18/18（Chromium + WebKit）。
- `scripts/verify-plan-079.sh`：`SUMMARY: BLOCKED fail=0 blocked=2`；BLOCKED 的两项是登录后真实页面走查（需要测试账号）和影子灰度（需要部署与一周观察）。

## 8. F7：PostgreSQL 排序规则版本告警（只读检查结果）

在只读事务里查系统目录（没有写任何东西，也没有读取口令以外的配置内容）：

| 项 | 结果 |
| --- | --- |
| 服务器 | PostgreSQL 16.15（Debian 12 容器镜像） |
| 库的排序规则 | `en_US.utf8`；**记录版本 2.41，当前实际 2.36**（即库建在较新的 glibc 上，现在运行在较旧的 glibc 上） |
| 依赖“命名排序规则”且版本不符的对象 | 0 个（873 个命名排序规则版本不符，但没有对象依赖它们） |
| 使用库默认排序规则的 btree 索引（`public`） | 92 个，其中唯一索引 57 个（主键、`uq_project_tenant_slug`、`tenant_slug_key`、`uq_translation_run_idempotency` 等） |

判断：glibc 版本变化只可能影响**字符串排序次序**，进而影响 btree 索引的有序性。主键基本是 UUID 字符串（ASCII 十六进制和连字符），在两个 glibc 版本里次序一致的概率很高，但**不能因此断言所有 57 个唯一索引都安全**（`slug`、`idempotency_key_hash`、各种 `*_key` 列可能含更多字符）。当前没有观察到查询异常或唯一约束异常，但这只是没有症状，不是证明。

下一步需要你批准（计划决策 D6，推荐 a）：在维护窗口里对这 92 个索引（至少 57 个唯一索引）逐个 `REINDEX INDEX CONCURRENTLY`，再执行 `ALTER DATABASE qyunslation REFRESH COLLATION VERSION`，告警随之消失。`REINDEX CONCURRENTLY` 不阻塞写入，但仍属于对生产库的写操作，我没有执行。更稳妥的选择是先装 `amcheck` 用 `bt_index_check` 验证现有索引是否真的失序，这需要扩展权限，也等你决定。

## 9. 需要用户动作的收口项：我能做的只读准备（均未执行任何写操作）

| 项 | 准备结果 | 仍需用户 |
| --- | --- | --- |
| F3 构建新鲜度 | 已提交的 `qyunslation/static/app` 与 `frontend/src` 的最后一次提交同为 `a672262`（2026-10-19），即**已提交的产物与已提交的源码一致**。工作区里 PLAN-079 的前端改动**尚未重新构建进 `static/app`**，上线前必须重新 `vite build` 并提交 | 确认发布窗口并执行；运行 QyunsApps 002g smoke |
| F9 配置核对 | `deploy/authentik/blueprints/README.md` 已写明：活动 SSOT 在 QyunsApps 仓，本仓蓝图只是恢复副本，且带 `client_secret` 占位默认值（在 Authentik 容器没有该环境变量时 apply 会把 secret 改成占位值）。这是 apply 前必须在 QyunsApps 侧确认的风险。没有接触任何密钥 | 在 QyunsApps 侧 apply 蓝图并做授权码往返 |
| F15 对象存储 | 决策包文档 `docs/assessments/object-storage-ownership.md` 已存在；T4 要求的 MinIO 实际配置、容量、备份证据在 qyunsgen 侧，本仓读不到，也不允许读取 access key | 补齐 5 项证据并决定是否迁移（D8） |
| F17 清理清单 | 已合并到 `main` 的本地分支 31 个（含 `feat/PLAN-077-qyunsapps-platform-adoption`、`fix/pg-loopback-binding`）；另有 9 个 worktree（其中 8 个挂在 `.codex`/`.cursor` 下，部分分支已合并）。**没有删除任何分支或 worktree**；有 worktree 占用的分支不能直接删 | 逐项确认（D10） |
| F0、F1、F4、F6、F7 的写入部分、F11、F13、F16 | 无可做的只读准备，或已在前文说明 | 见 PLAN-079 §11 |

## 10. 上线前的 legacy 行为核对（修正）

本文 §1 原来写“不部署也不会改变现有行为”，逐项核对后这句话不成立。默认配置下的实际变化如下：

| 项 | 默认配置下是否生效 | 影响 |
| --- | --- | --- |
| 术语门禁 `legacy/shadow/enforce` | 默认 `legacy`，门禁口径不变 | 无 |
| 乱码源文继承降级 | **默认 auto**（`QYUNSLATION_ENCODING_INHERITANCE`=0/1/auto） | 仅未映射标记且不多于源文时降为警告；新增乱码、C1、mojibake 仍阻断 |
| 乱码正则收紧 | **生效** | 大写葡/西语名（`JOÃO`、`SÃO PAULO`）不再被判为乱码。这是对误报的修正，但它确实减少了一类阻断，需要知道 |
| 预检复用时的语言提示 | **生效** | 复用预检时按新选的源语言重算语言提示（修正） |
| docx/pptx 工作流 | **生效** | `factory.py` 此前把 `domain_profile`/`document_profile` 传给翻译器配置，所有翻译器 dataclass 都不接受，docx/pptx 经该路径会 `TypeError`。在 `main` 上已复现（`test_plan060_evidence` 在干净工作树上失败）。修复后这条路径可用 |
| 工作台加载失败提示、网络中断保留上传指针 | **生效** | 只影响提示文案和本地指针，不影响任务 |
| 前端 A（对照视图定位） | **生效** | 定位行为修正，已浏览器实测 |

**结论：** 部署后的默认行为与之前相比，门禁不变；乱码阻断在“大写葡/西语名”上放宽，docx/pptx 从报错变为可用，其余为 UI 修正。源文继承降级和 E2/E3 影子灰度都没有在默认路径上启用。


## 11. 上线记录（2026-10-19）

- 提交：`4ade192`（docs）、`018dda7`（后端）、`e5c7d79`（前端）、`134ec71`（构建产物），合并为 `183d6c0`（`--no-ff`），已推送 `origin/main` 与 `origin/docs/plan-079-qa-gate-triage`。
- 部署：`scripts/deploy-translate-stack.sh` 在 `183d6c0` 上运行。部署前门禁：迁移对齐（`078e0001`，无新迁移）、前端构建新鲜、路由探测通过；sidecar 指纹 `7542777de0fd` 本地与线上一致；`pdf2zh.service`、`qyunslation-office.service` 均 active。
- 部署时运行中的翻译任务：0；运行中的 QA 轮次：0。
- 线上核对：8010 的 `/next/` 引用新资源 `index-DIydkICa.js`；`/api/v1/settings/schema` 未登录返回 401；7860 返回 200（pdf2zh 重启后约 5 秒就绪）。日志中唯一匹配 "error" 的一行是 OCR 能力状态（`vision: stub`），不是故障。
- **门禁模式：部署时为 `legacy`（默认）。`shadow` 观察尚未开始**，见 §12。

## 12. 尚需用户手动完成的步骤（含命令）

所有命令在 `/home/dev/qyunslation` 下执行。需要读取 `.env` 的命令都用子 shell 加载，且不打印取值。

**E2：开启 shadow 观察（需要你确认后再做，它开始计一周的观察期）**

```bash
mkdir -p ~/.config/systemd/user/qyunslation-office.service.d
printf '[Service]\nEnvironment=QYUNSLATION_TERM_GATE_MODE=shadow\n' \
  > ~/.config/systemd/user/qyunslation-office.service.d/plan079-mode.conf
systemctl --user daemon-reload          # 当前 pdf2zh 的 NeedDaemonReload=no，reload 不会改动它
systemctl --user restart qyunslation-office.service
systemctl --user is-active qyunslation-office.service
```

一周后看差异报告（只读）：

```bash
(set -a; . ./.env >/dev/null 2>&1; set +a; .venv/bin/python scripts/qa/plan079_shadow_report.py --limit 50)
```

逐个抽查 `inspect_released_runs`（旧口径阻断、新口径放行的任务），确认没有真实高风险缺陷被放过。

**E3：切换为 enforce（抽查通过后）**

```bash
printf '[Service]\nEnvironment=QYUNSLATION_TERM_GATE_MODE=enforce\n' \
  > ~/.config/systemd/user/qyunslation-office.service.d/plan079-mode.conf
systemctl --user daemon-reload && systemctl --user restart qyunslation-office.service
```

**回滚（任何时候）：**

```bash
rm ~/.config/systemd/user/qyunslation-office.service.d/plan079-mode.conf
systemctl --user daemon-reload && systemctl --user restart qyunslation-office.service
```

**F0：确认生产 PostgreSQL 口令（只看是否为默认值，不打印取值）**

```bash
if ! grep -q '^QYUNSLATION_PG_PASSWORD=.\+' .env; then echo "未设置：compose 使用默认值，需要轮换"
elif grep -q '^QYUNSLATION_PG_PASSWORD=qyunslation_dev_only$' .env; then echo "仍是默认值，需要轮换"
else echo "已自定义"; fi
```

如需轮换，要先停机，并核对 `docs/runbooks/pg-loopback-binding.md`。注意：改 `.env` 里的变量不会改已初始化数据库的密码，必须在数据库内执行 `ALTER USER ... PASSWORD ...`。

**数据库命令的前提：** 本机没有 `psql`、`pg_dump`，数据库在容器 `qyunslation-plan034c-pg` 里，用容器自带的客户端执行。`<db-user>` 请从 `.env` 中的 `QYUNSLATION_DATABASE_URL` 取用户名（只打印用户名，不要打印密码）：

```bash
grep -o '^QYUNSLATION_DATABASE_URL=postgresql+psycopg://[^:]*' .env | sed 's/.*:\/\///'
```

**F4：术语证据回填（写生产库，需批准）。** 任务 ID 为 `eb7e4876-d6af-4ca8-9a4b-249a778cd35c`。

```bash
set -a; . ./.env >/dev/null 2>&1; set +a
# 先备份候选表（D5 推荐）
docker exec qyunslation-plan034c-pg pg_dump -U <db-user> --data-only \
  -t document_term_candidate -t document_term_occurrence qyunslation > "backup-term-$(date +%F).sql"
.venv/bin/python scripts/backfill-term-evidence-sentences.py eb7e4876-d6af-4ca8-9a4b-249a778cd35c          # 只演练
.venv/bin/python scripts/backfill-term-evidence-sentences.py eb7e4876-d6af-4ca8-9a4b-249a778cd35c --apply  # 确认演练结果后
```

**F7：排序规则版本告警（写生产库，需维护窗口和批准）**

```bash
# 1. 生成逐个索引的 REINDEX 清单（只读），先审阅
docker exec qyunslation-plan034c-pg psql -U <db-user> -d qyunslation -At -c "select 'REINDEX INDEX CONCURRENTLY '||quote_ident(n.nspname)||'.'||quote_ident(ic.relname)||';' from pg_index i join pg_class ic on ic.oid=i.indexrelid join pg_class tc on tc.oid=i.indrelid join pg_namespace n on n.oid=tc.relnamespace join pg_am am on am.oid=ic.relam and am.amname='btree' where n.nspname='public' and exists (select 1 from unnest(string_to_array(i.indcollation::text,' ')::oid[]) o where o=100)" > reindex.sql
wc -l reindex.sql
# 2. 批准后执行 REINDEX（逐条，CONCURRENTLY 不能放在事务里），再刷新版本
docker exec -i qyunslation-plan034c-pg psql -U <db-user> -d qyunslation < reindex.sql
docker exec qyunslation-plan034c-pg psql -U <db-user> -d qyunslation -c "ALTER DATABASE qyunslation REFRESH COLLATION VERSION;"
docker exec qyunslation-plan034c-pg psql -U <db-user> -d qyunslation -c "select datcollversion, pg_database_collation_actual_version(oid) from pg_database where datname=current_database();"
```

两个版本相等即完成。需要数据库属主权限。

**F3：线上 SSO/边缘 smoke（QyunsApps 002g）**

仓库里的 `QyunsApps/tests/adopters/qyunslation-qyuns-browser.mjs` 用的是拦截请求的本地构建，不会访问真实服务。真实 SSO/边缘 smoke 按 QyunsApps 002g 的 runbook 执行。本地的离线检查：

```bash
cd /home/dev/QyunsApps && QYUNSLATION_REPO=/home/dev/qyunslation node tests/adopters/qyunslation-qyuns-browser.mjs
```

**F1：登录后的真实页面走查（需要测试账号，不要把账号密码发到对话里）**

打开 `https://translate.qyunsgen.com/next/workbench`，登录后检查：运行详情的 QA 待办、点"在对照视图定位"；术语审核中的逐条出处与完整句子；参数确认抽屉（只打开，不提交）；不点击批准、清除、翻译。结论告诉我，我记入 WT-079。

**F9：QyunsApps 侧应用 Authentik 蓝图并做授权码往返（在 QyunsApps 仓执行）**

```bash
cd /home/dev/QyunsApps && python3 authentik/scripts/blueprint_check.py    # 先检查
# 按 QyunsApps 的 authentik 应用流程执行 apply（由你完成）
```

然后在浏览器里走一次 SSO 登录和登出。本仓蓝图的 `client_secret` 占位风险见 `deploy/authentik/blueprints/README.md`，apply 前务必确认容器里已设置真实的 `QYUNSLATION_OIDC_CLIENT_SECRET`。

**F15：对象存储决策证据（只能由你读取）**

证据清单见 `docs/assessments/object-storage-ownership.md` 的表格。第 1、2、4 项需要你在 qyunsgen 侧查看（例如 `mc du <alias>/<bucket>`，`<alias>` 是你本地的 mc 别名）。不要把 access key 发给我。

**F13：f8 导航层级的决策**

在 WT-078 的 f8 评估里选 A/B/C 之一，然后对方案做截图对比。这一步没有命令。

**F16：Authentik runtime 迁出**

需要 QyunsApps 002e 的单独批准。本次不做。

**F17：分支与 worktree 清理（逐项确认后删除）**

```bash
git branch --merged main | sed 's/^[+* ]*//'        # 已合并的分支，先审阅
git worktree list                                    # 先列 worktree，它们会占用分支
git worktree remove <path>                           # 对每个待删除的 worktree 逐个执行
git branch -d <name>                                 # 只删已合并的分支
```

`feat/PLAN-077-qyunsapps-platform-adoption` 的 worktree 在 `/home/dev/.codex/worktrees/qyunsapps-plan002/qyunslation-plan077`，要先移除 worktree 才能删分支。未合并分支按 D10 保留。

**决策 D5–D10（推荐项）**

| 决策 | 推荐 | 对应步骤 |
| --- | --- | --- |
| D5 回填方式 | a：逐个任务演练后 `--apply`，写入前备份 | F4 |
| D6 排序规则刷新 | a：先只读检查，逐个 REINDEX，再刷新版本 | F7 |
| D7 文档分支合并时机 | a：已随阶段 A 代码合并，无需再做 | F11（已完成） |
| D8 对象存储迁移 | a：先补证据，决定前不迁移 | F15 |
| D9 Authentik 迁出 | a：另立计划，单独批准 | F16 |
| D10 分支清理 | a：只删已合并分支 | F17 |

**还未发生的事：** E2/E3 的观察与切换、F0、F1、F3 的 SSO smoke、F4、F7、F9、F13、F15、F16、F17。F6 的 `pdf2zh.service` 单元状态经核对已是 `NeedDaemonReload=no`，视为完成；如需审阅单元内容，用 `systemctl --user cat pdf2zh.service`。

## 13. 上线后反馈与修复（2026-10-19）

用户登录生产后反馈：定位已经能跳页；但乱码阻断点"确认误报"和"驳回误报反馈"都清不掉；术语审核一篇文献有上百条，太耽误时间。

**乱码阻断（根因：设计对单人不友好，不是失灵）。** 乱码属于 C1（关键事实）。C1 的规则是“反馈误报 → 另一个人（管理员/术语管理员/所有者）确认误报”才会清除；反馈人自己确认会被拒绝（`NEEDS_SECOND_PERSON`）。“驳回误报反馈”的意思是“问题确实存在”，阻断保留；截图里的理由“未见乱码，内容可以接受”其实是误报的意思，却选了驳回。单人使用时这类阻断永远清不掉。

用户选择的方案（调整原先确认过的两人确认规则，仅限乱码这一类）：
- `TEXT_ENCODING_ARTIFACT` 从 C1 改为 C2：**复核人写 ≥10 字理由授权例外即可放行，一个人，记入审计**。数字、否定、剂量等其他关键事实类仍是 C1，仍需第二人确认。
- 已经存放在库里、类别为 C1 的乱码条目也按 C2 处理（`registry.RECLASSIFIED`），不需要重新检查。
- 按钮文案：“驳回误报反馈”改为“驳回（问题确实存在）”，并说明“想说这是误报、可以放行不要点这个”；“授权例外”的说明加上乱码。

**术语审核太多。** 当时的规则更新只有一份 30 条的统计方法短语表（PLAN-079 v1），不够。最近一个任务里 70 条是 `deterministic:abbreviation`（正则 `\b[A-Z]{3,}\b` 抓到的所有大写词），其中 40 条只出现一次，只有 21 条在原文里带括号定义。处理：
- 确定性抽取：缩写只在**出现 ≥2 次或原文带括号定义**时才列为候选；药名、靶点、编码、研究编号、疾病、机制不受影响。
- **门禁改为 `enforce`**（用户选择，跳过一周 shadow）：普通词库候选不再阻断交付，也不要求逐条审核；与批准译名冲突、同一术语多种译法、术语库别名冲突、硬约束漏用等真实缺陷仍会阻断。
- 非阻断时候选列表默认折叠，只显示一行摘要。

**风险与限制：** `enforce` 没有经过 shadow 观察期；只有一个任务的样本。缩写过滤会少列一些只出现一次且无定义的缩写，它们仍可在后续任务里因重复出现被列出。乱码放行现在只靠复核人看页面，没有第二人把关。

### 13.1 上线记录

- 提交 `c8f653e`（修复）、`96bb1cd`（构建产物），已推送 `origin/main`；`scripts/deploy-translate-stack.sh` 在 `96bb1cd` 上运行，前置门禁与路由探测通过，两个服务 active，7860 返回 200。部署时运行中的任务与 QA 轮次均为 0，无迁移。
- 门禁模式：**`enforce`**，通过 systemd drop-in `~/.config/systemd/user/qyunslation-office.service.d/plan079-mode.conf` 设置，线上进程环境里已确认。回滚：删除该文件，`systemctl --user daemon-reload && systemctl --user restart qyunslation-office.service`，门禁回到 `legacy`。
- 现网任务 `eb7e4876` 只读核对：门禁原因只剩 `qa_blockers`；123 条候选仅作显示。当前 4 个阻断：两个乱码（现为 C2，复核人可授权例外）、一个作者元数据（C2，可授权例外）、**一个 `LITERAL_MISSING_IND`（申报编号缺失，仍是 C1：必须修复，或由另一位管理员确认误报）**。最后这一个不在本次放宽范围内。

## 14. 阻断项给出可点击的解决方案（2026-10-19）

**反馈：** 发现阻断项后只告诉“怎么处理”的一段文字，真正的操作是“授权例外/反馈误报”这类动作名，头部另有一个与具体问题无关的“生成修订版”；阻断了、报告了，就没有下文。

**做法：** 每个阻断项（含警告）下新增“怎么解决”区，按推荐顺序列出针对这个问题的选项，每个都是能执行的按钮；服务端按问题类别、当前账号的权限和任务状态过滤后下发（`QaItem.remedies`，目录在 `registry.remedies_for`）。

| 问题类别 | 推荐 | 其他选项 |
| --- | --- | --- |
| 关键事实类（C1：数字、否定、编号、邮箱、漏译、残留标记） | 重新生成修订版（原版保留，同配置重译并自动复检） | 先看页面；“我核对过，这是检查误报”（理由已预填，仍需第二人确认） |
| 版式/元数据/乱码（C2） | 确认没问题，带着交付（**理由已按问题类型预填，可改**，一个复核人即可） | 先看页面；重新生成修订版 |
| 检查没跑成（C3） | 重新检查 | — |
| 术语（C4） | 去术语工作台核对译名（**直接带着该术语搜索**） | 按批准译名重新生成修订版；本文确需这样翻，带着交付 |
| 警告（W） | 已阅，不影响交付（理由已预填） | 先看页面 |

- “带着交付”类选项会打开原来的表单，**理由已填好且可修改**，核对完点一次提交即可；理由仍是至少 10 个字并记入审计，规则没有放宽。
- 当前账号没有任何可执行的选项时（例如提交人本人不能授权例外），明确提示联系哪些角色，不再只是空着。
- 术语工作台支持 `?q=` 预填搜索。

**没有做、也不能一键做的：** 对译文文字做原位修改。输出是 PDF，段落级原位修订与局部重译依赖对象锚点（见 PLAN-078 总纲“后续增强”），是一个单独的大功能。所以“修正”目前的含义是：重新生成修订版、改好词库后重新生成，或经复核人写理由放行；不是就地改字。

**验证：** 后端新增 `test_plan079_remedies.py`（每类问题恰好一个推荐、预填理由≥10 字且动作与类别匹配、按权限过滤）和端到端用例；前端 5 项（推荐项突出、预填理由可直接提交、重新检查真正调用接口、术语跳转带搜索、无权限时说明联系谁）；真实浏览器 Chromium + WebKit × 三种宽度共 102 项通过，含“按钮显示、推荐项标记、理由预填且可提交”。

### 14.1 上线记录

- 提交 `ebee221`（功能）、`5543c7e`（文档）、`a2cad91`（构建产物）已推送 `origin/main`；`scripts/deploy-translate-stack.sh` 在 `a2cad91` 上运行，前置门禁与路由探测通过，两个服务 active，7860 返回 200。
- 部署时运行中的任务与 QA 轮次均为 0，无迁移。门禁仍为 `enforce`（systemd drop-in，线上进程环境已确认）。
- 线上前端已切换为新构建 `index-BcN5MwIo.js`；接口未登录返回 401。**未在真实登录环境下查看解决方案按钮**，这一步需要你登录后确认。

## 15. 解决方案区的二次修复与界面重设计（2026-10-19）

用户上线后反馈两点：(1) 点“我核对过，这是检查误报”提交后，阻断没有被清除；(2) 解决方案做成了整行长条，太丑。

**(1) 为什么没清除，以及怎么改。** 那个按钮提交的是“反馈误报”，不是放行；关键事实类（C1）的规则是反馈后要有人“确认误报”才清除，而“确认”原来**不允许反馈人自己做**（`NEEDS_SECOND_PERSON`）。单人使用时这条路是死胡同，而界面没有说明提交后卡在哪里。用户选择放宽（推荐项）：
- **有确认权限的角色（术语管理员、管理员、所有者）可以确认自己的反馈**，审计里该条记录标注 `self_review`（自我确认），反馈和确认两条记录都保留。普通复核人和提交人仍然不能确认。
- 有确认权限的人看到的是**“核对过了，这是检查误报，放行”**，一次提交依次记录“反馈误报”和“确认误报”（表单里写明会记两条）；没有确认权限的人看到“我核对过，这是检查误报”，提交后需要有确认权限的人确认。
- **“已反馈、待确认”状态不再是死胡同**：有确认权限的人看到“确认这是误报，放行”（推荐）/“驳回：问题确实存在”/先看页面/重新生成；没有确认权限的人看到明确说明“已反馈误报，等待有确认权限的人确认，角色是……”，并推荐“重新生成修订版”。
- 数字、否定、编号等**其他关键事实类的判定没有变**，只是确认人可以是反馈人本人。

**(2) 界面。** 原来每个选项一整行、说明各占一行，4 个选项占掉大半屏。改为：
- 选项是**紧凑的一行**（胶囊按钮，手机上自然换行、触控高度 ≥44px）；推荐项实心突出并带“推荐”标签，其余为描边按钮。
- 下面**只有一行说明**：默认是推荐项的说明，鼠标悬停或键盘聚焦到某个选项时换成它的说明（`aria-describedby`，读屏可读）。
- 原来的“反馈误报/确认误报/驳回”三个手动按钮折叠进“更多处置方式”，因为它们与解决方案重复；表单紧跟在解决方案下面出现。
- 已有提示条（“已反馈，等待确认”）用琥珀色左边线的提示块。

**验证：** 后端新增端到端用例（确认人单人完成、审计标注、普通复核人仍被拒、待确认状态下的下一步）和 `test_plan079_remedies.py` 的待确认用例；前端新增“一步反馈+确认”“待确认仍有可点击项”“一行说明随聚焦变化”；真实浏览器 Chromium + WebKit × 三种宽度共 124 项通过，含“按钮紧凑不是整行长条、桌面端同一行、手机触控≥44px、只有一行说明”。

**风险：** 管理员/所有者可以单人放行关键事实类的误报，没有第二个人复核；审计里能查到哪些是自我确认（`self_review`）。要收紧时，把 `_apply_disposition` 里的 `self_confirm` 分支改回拒绝即可。

### 15.1 上线记录

- 提交 `0848e2a`（修复与重设计）、`941b02e`（文档）、`399acfe`（构建产物）已推送 `origin/main`；`scripts/deploy-translate-stack.sh` 在 `399acfe` 上运行，前置门禁与路由探测通过，两个服务 active，7860 返回 200，日志无异常。部署时运行中的任务与 QA 轮次均为 0，无迁移，门禁仍为 `enforce`。
- 线上前端为 `index-C-M7HV5D.js`；接口未登录返回 401。
- 现网任务 `eb7e4876` 的只读核对：`LITERAL_MISSING_IND` 处于“已反馈误报，待确认”。以有确认权限的角色查看，选项是 `locate / confirm（推荐）/ reject / revise`；以普通复核人查看，是“等待有确认权限的人确认”并推荐重新生成。两个乱码条目一个已授权例外，另一个与作者元数据一样，推荐“确认没问题，带着交付”。
- **未在真实登录环境下点过新界面**，需要你登录后确认。

## 16. 重新生成后重复确认、批准后找不到导出（2026-10-19）

用户反馈三点：(1) 已确认过的误报，重新生成修订版后又报了一遍；(2) 批准正式稿后没有导出按钮，退出 QA 才看到；(3) 希望点“批准”后自动进入完成页面，并且还能回到 QA 页继续修改、更新生成结果。

**(1) 重复确认。** 只读核对现网：同一个 `PIND######` 编号缺失在版本 1 和版本 2 里是**指纹完全相同的发现**，版本 1 的处置是对的，但系统按设计“新版输出变了就不自动沿用旧结论”，所以必须在新版上重来。这个设计保留（它防止旧结论悄悄盖住不同的输出），改成**一键沿用**：
- 同一指纹的发现在新版里原样出现、上一版已有结论时，该条的解决方案第一项是**“沿用上一版的结论”**（推荐）：理由已按上一版预填，动作与上一版一致（授权例外 / 确认误报 / 已阅）。对误报，有确认权限的人一次完成“反馈 + 确认”，没有确认权限的人只能重新反馈。
- 列表顶部新增**“沿用上一版的全部结论（N 项）”**，逐项依次提交；任何一项失败就停下并说明已处理几项。每一项仍是单独的、记入审计的处置，没有放宽规则，也没有静默继承。
- 这条规则本身仍在把同一个编号判为缺失：它是否是规则误判值得单独查（需要看原文里编号的写法），本次没有改规则。

**(2)(3) 完成页。**
- 新页面 `/workbench/:runId/complete`：绿色对勾“正式稿已生成”，**每个正式文件一个下载按钮**（含大小），在线预览，“回到质量检查”“回到任务列表”；明确写出“生成修订版会产生新版本，当前这一版的正式稿会保留，仍可下载”。没有批准的版本只显示说明，不显示下载。
- **点“批准正式产物”成功后自动跳转到完成页**；批准失败留在 QA 页并显示原因。
- QA 页：已批准的版本头部多了“**前往导出**”和“**生成修订版**”；任务列表里已完成的任务入口变为“导出”。
- 后端：**已完成（已批准）的版本现在允许生成修订版**（之前明确不允许），这是“回到 QA 修改并更新结果”的前提。新版本是新一代，旧版本被取代但**保留文件和下载**。

**验证：** 后端新增端到端用例（同一发现跨版本沿用、已批准版本可修订且旧版文件保留）；前端 `runComplete.test.js` 4 项、批准后跳转/失败留在原页/已批准版本的链接与按钮/沿用全部/中途失败停下共 5 项；真实浏览器 Chromium + WebKit × 桌面/手机共 40 项：点批准 → 自动到完成页 → 看到两个下载按钮且可见 → 回到 QA 页 → 看到“前往导出”“生成修订版”，批准只发送一次。

**限制与风险：** 对已批准版本生成修订版会产生新一代并让旧版本显示“已被更新版本取代”；旧版文件仍可下载，但需要使用者自己分清哪一版是当前版本。没有在真实登录环境下走过这条流程。

### 16.1 上线记录

- 提交 `fb8dcd9`（功能）、`83b99a7`（文档）、`860b3ee`（构建产物）已推送 `origin/main`；`scripts/deploy-translate-stack.sh` 在 `860b3ee` 上运行，前置门禁与路由探测通过，两个服务 active，7860 返回 200，日志无异常。部署时运行中的任务与 QA 轮次均为 0，无迁移，门禁仍为 `enforce`。
- 线上前端为 `index-BCTMsBMs.js`；接口未登录返回 401；完成页路由 `/next/workbench/:runId/complete` 返回 200。
- **未在真实登录环境下走过“批准 → 完成页 → 下载 → 回到 QA”这条流程**，需要你登录后确认。

## 17. 生产界面只读复核（2026-10-21）

**范围与方式：** 登录身份 `charlie780405`（租户 pilot，角色含 admin），只读查看，未点击任何处置、放行、导出按钮，未提交任何写操作。

**复核对象说明：** 原定任务 `eb7e4876`（Jiangsu PIND 182646 会议纪要 v1，`gated`）在 2026-10-20 04:46 UTC 已被移入回收站，详情接口对回收站任务返回 404，属设计行为。用户在界面恢复了 `a3887b13`（`50-LIT-2026-MGK10-Trial.pdf`，`gated`，`qa_blocked`）后，改以该任务复核。`eb7e4876` 未被恢复。

**已确认（页面与数据库一致）：**
- 任务头部：`待处理质量问题 · 阶段 质量检查 · 质量 有阻断问题`，提供“重新检查”“放弃本版本”“生成修订版”。
- 阻断问题 1 项：`TEXT_ENCODING_ARTIFACT`（译文第 2 页，检测器 `U+FFFD`，已与源文对照，`rule_version=qa-b8b9714130c8`）；警告 2 项 `TEXT_ENCODING_INHERITED`（源文同页也存在）；词库待整理 84 条，不影响交付；正式稿显示“未解锁”。
- 解决方案区按“哪里有问题 / 为什么影响交付 / 怎么处理 / 怎么解决”分块；提供“在对照视图定位”“确认没问题，带着交付（推荐）”“重新生成修订版”；折叠区“更多处置方式”含“反馈误报”“授权例外”“撤销例外”；“技术详情”折叠，展开可见码点与页码。
- “确认没问题，带着交付”的说明为“一个复核人即可，理由会记入审计，之后可以撤销”。

### 17.1 写操作复核（用户授权，仅限 `a3887b13`，已还原）

| 项目 | 结果 |
|---|---|
| “在对照视图定位” | 通过：地址带 `page=2`，切到“译文”，页码 2/11，提示“已定位到译文第 2 页” |
| 理由过短 | 通过：理由不足 10 字时“提交”为禁用，未写入 |
| 无例外时“撤销例外” | 通过：提示“这条问题没有可撤销的例外”，库中无新增记录（原疑点 1 已解决） |
| “授权例外”（理由 ≥10 字） | 通过：提示“已记录：授权例外”，阻断数 0，任务进入“待人工复核”，“批准正式产物”可用（未点击）；`qa_disposition` 新增 `grant_waiver / admin / self_review=t` |
| 自审标识 | 通过：处置记录显示“（提交人自审）”；该类问题（版式/元数据/乱码/术语）说明为“一个复核人即可”，页面未设第二人确认门槛 |
| “撤销例外”（有例外时） | 通过：提示“已记录：撤销例外”，阻断问题回到“待处理”，任务回到 `gated / qa_blocked / qa`；新增 `revoke_waiver / admin / self_review=t` |

**留下的审计记录：** `a3887b13` 上新增 2 条（`grant_waiver`、`revoke_waiver`，理由均以“[PLAN-087 复核测试]”开头），审计表只追加，不删除。**未批准、未导出、未放弃版本、未生成修订版。**

**仍未验证：** 批准后的完成页与导出入口；需要第二人确认的类别（如 `LITERAL_MISSING_IND`，见 §15）在该任务上不存在。

**观察到的疑点（待核实，不下结论）：**
1. 已授权例外的阻断项详情里，“怎么解决”区显示“当前账号对这一项没有可执行的操作。请联系有复核权限的同事……”，而当前账号是 admin，提示措辞容易误导；实际“撤销例外”在“更多处置方式”里可用。
2. 旧任务 `eb7e4876` 的 5 条处置记录里，4 条 `self_review=t`（3 条 `grant_waiver`、1 条 `confirm_false_positive`，均为 admin，发生在 2026-10-19）。这些记录是否符合 §15/§16 对“第二人确认”的要求，本次没有核对规则实现，**未下结论**；该任务在回收站，暂不处理，如需结论应对照 `qa_disposition.self_review` 的写入逻辑再核。

**现场状态：** 仅恢复了 `a3887b13` 一个任务（用户操作）并完成上述写操作复核，现已还原为 `gated / qa_blocked`；`eb7e4876` 仍在回收站（保留至 2026-11-19）。

## 18. 试行部署与完成页验收（2026-10-21）

- 部署：从 `main`（`9d3e58ad`）执行 `scripts/deploy-translate-stack.sh`，前置门禁、指纹 `7542777de0fd` 核对与后置门禁均 PASS；`qyunslation-office` 与 `pdf2zh` 均为 active；`translate.qyunsgen.com/next/workbench` 与 `/api/v1/health` 返回 200。
- 删除 `docker-compose.plan034c.yml`（含默认口令回退），同步移除 `scripts/verify-plan-034c.sh` 的存在性校验；PG 容器不受影响。
- 完成页与导出验收：对已批准任务 `d33c1ab8` 只读核对，完成页与两个 PDF 下载链接均可用（206，`%PDF-`）。
- 未对 `a3887b13` 批准：其唯一阻断项为 `TEXT_ENCODING_ARTIFACT`（译文第 2 页 `U+FFFD`），不以授权例外放行。
