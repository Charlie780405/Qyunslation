# PLAN-076 AD 内部测试版 · 生产证据（2026-10-03）

环境：https://translate.qyunsgen.com，`QYUNSLATION_AD_PROMPT_MODE=pilot`、`QYUNSLATION_AD_PROMPT_TENANTS=pilot`（仅 allowlist 测试租户），模型 `internal-qwen-quality`（qwen3.6:35b-a3b），pipeline v2，office 执行器。操作账号 `test02@qyunslation.com`（term_admin / can_review）经 Authentik OIDC → BFF cookie 登录；浏览器为 Playwright Chromium（Chrome for Testing 153），不保存 token、密码或 session 文件到仓库。

## 四条真实浏览器流程（UI 操作，截图为 1440 宽全页）

| 方向 × 文档类型 | 文件 | 截图前缀 | 结果 |
| --- | --- | --- | --- |
| en-zh · 医学研究文献 | ad-en-zh-001.docx | `ad-en-zh-001-ui-0{0..4}-*.png` | review_ready → UI「批准正式产物」→ approved，正式 docx 下载 200 |
| en-zh · 临床研究文档 | ad-en-zh-003.docx | `ad-en-zh-003-ui-0{0..4}-*.png` | 同上 |
| zh-en · 医学研究文献 | ad-zh-en-001.docx | `ad-zh-en-001-ui-0{0..4}-*.png` | 同上 |
| zh-en · 临床研究文档 | ad-zh-en-002.docx | `ad-zh-en-002-ui-0{0..4}-*.png` | 同上 |

每组截图依次为：`00-configured`（语言对、专业领域 = AD 特应性皮炎 + 「AD 内部测试版」徽标、文档类型）、`01-preflight`（预检通过）、`02-running`（任务创建）、`03-review`（运行详情：`提示词 076-v1 · ad.<dir>.<profile>.translate.v1 · sha256:…`、阶段事件到「确定性 QA 通过 / 等待人工审校」、批准按钮）、`04-approved`（批准后）。

## pilot soak（≥20 任务，每格 ≥5）

- 输入：`pilot-soak-20261003.json`（任务级：case、方向、文档类型、prompt 版本/摘要、termbase 版本、term policy 摘要、注入术语数、模型、pipeline、执行器、延迟、token、QA 阻断码）。
- 门禁输出：`pilot-report-20261003.json`（`scripts/plan076-ad-eval.py --pilot-report` 原始报告），**PASS**：22 个已批准 AD 任务，格计数 5/5/5/7，高风险事实错误 0，药名漂移 0，P95 延迟比 1.0744，P95 token 比 1.1059（阈值 ≤ 1.25）。
- baseline：同一批文档在同一租户、同一模型下以 `domain_profile=general` 跑 8 个任务（每格 2 个），P95 延迟 17330 ms、P95 token 8690；pilot P95 18620 ms / 9610。延迟与 token 定义见 soak 文件头部（均取自 office sidecar 日志，同口径）。
- 阻断：3 份文档被确定性 QA 以 `AD_NUMBER_DRIFT` 拦截，批准请求均被 409 拒绝（`approve_blocked`）：
  - ad-zh-en-009：源文「1 955篇文献」在译文中被整体丢失，重译一代（generation 3）仍丢失 → 真实遗漏，拦截正确；
  - ad-en-zh-005：通讯地址邮编「110 001」与一处引用计数在译文中丢失 → 真实遗漏（低风险位置），拦截正确；
  - ad-en-zh-008：`IQR 25–75%` 被改写为「第 25–75 百分位数」，语义等价但丢失 `%` → 需人工判读，交由审校。
- 提示词摘要在 4 个格内各自唯一，且在当天 8 次服务重启（6 次部署 + 2 次）前后不变；`var/ad-audit/rollout-mode.json` = `{"mode":"pilot","tenants":["pilot"]}`，`ad-events-20261003.jsonl` 含 1 条 `rollout_mode_change` 与全部 `ad_task_created`。
- 服务重启恢复：首个 AD 任务（734ab988）在部署重启后由心跳判定 `interrupted`，经 `/resume` 续跑后 review_ready → 批准 → 下载 200，prompt 摘要前后一致。

## soak 期间发现并修复的发布阻断缺陷（均已部署并带回归测试）

| 提交 | 缺陷 |
| --- | --- |
| `bf913fd` | 每次重启后首个带 cookie 的请求 503 `web session store unavailable`（引擎惰性初始化晚于 require_identity） |
| `0c120ef` | 同一预检第二次建任务 500（唯一约束）→ 409 `PREFLIGHT_ALREADY_RUN` |
| `e6f830b` | pipeline v2 下 docx/pptx/txt/图片任务永远停在 translating/layout，不跑 QA、批准后不物化产物 |
| `6bb2c2c` | 零发现的 AD 任务每次轮询重复跑 QA，事件账本被「版式完成/QA 通过」刷屏（600+ 行） |
| `db36870` | 审校 reject 后被执行器残留状态复活为 translating，`/retry` 永远 409 |
| `00e7449` / `376657d` | AD 任务 retry 新代缺冻结提示词，启动即 `AD prompt digest mismatch` |

## 专家双盲（真人项，BLOCKED）

`var/plan076-expert-pack/`（不入库）已导出 24 例 A/B 盲评包（`cases/<id>/{source,A,B}.txt`、两份评审表、`rubric.md`、`adjudicator/key.json`）。需 AD 医学专家与医学翻译专家各自填写后，用 `scripts/plan076-ad-eval.py --expert-review <json>` 聚合。本目录不含任何模拟评分。
