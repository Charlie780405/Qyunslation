# WT-076：AD 中英双向专业翻译发布证据

> 对应计划：[PLAN-076](../plans/PLAN-076-ad-bilingual-prompt-quality-system/README.md)
> 当前状态：**076i 代码在 `c0b5a8b`。OA 双向语料与模型双跑已完成，硬门与模型对比未通过；DeepSeek 双角色结果只是模拟，不是专家验证。生产 AD 模式保持关闭。**

## 交付范围

PLAN-076 只覆盖简体中文 ↔ English 的特应性皮炎（AD）专业翻译：

- 版本化双向提示词编译、运行时注入和 metadata-only prompt snapshot；
- AD 静态术语表、方向反转、风险级别和不可翻译字段；
- 数字/剂量、术语、否定和情态四类确定性 QA；
- 高风险片段语义复核接口及最多一次受保护修复；
- 工作台 AD 专业模式选择、运行详情标识和提示词版本摘要；
- 发布评估脚本，缺少授权真实语料时 fail-closed 为 BLOCKED。
- 总门禁要求同时生成 generic baseline 与 AD candidate 的不可覆盖 model run；只对参考译文做 QA 不再可判 PASS。

## 代码提交

| 提交 | 内容 |
| --- | --- |
| `766c189` | AD 提示词、术语、确定性 QA、API/运行时/UI 垂直切片 |
| `df90fd8` | 有界语义 QA、修复保护、运行详情元数据和回归修复 |
| `84d3b1d` | AD rollout 环境门禁，生产默认关闭 |
| `43baf51` | 双向评估脚本、测试语料契约、总门禁和静态包 |
| `afbd1d0` | 修正 `--direction` 筛选、补充 API 合约回归和评估器测试 |
| `523f1fa` | 将评估器回归纳入总门禁 |
| `fe6cd45` | 实现 `AD_PROMPT_MODE` 与 pilot 租户 allowlist，生产 fail-closed |
| `aa5e06e` | 简化 rollout policy 边界，保持 fail-closed 行为 |
| `09db35f` | 修复显式 OIDC 高权限对已有低权限 membership 的晋升 |
| `97d386f` | 增加 AD 语料 manifest/schema、哈希与授权完整性门禁 |
| `9e7db80` | 评测仅读取锁定 manifest case；baseline-only 在模型运行器接入前 fail-closed |
| `a16fb44` | 接入不可覆盖 generic/candidate model run、annotation schema 和公网端点 fail-closed |
| `537aef9` | 评测报告剥离端点内嵌凭据 |
| `51af1e5` | 增加 pilot soak 与专家双盲聚合门禁；缺证据保持 BLOCKED |
| `a61fbed` | 工作台明确显示 AD「内部测试版」状态 |
| `4d57870` | 重新构建并发布包含内部测试版文案的静态包 |

不包含用户本机的 `.cursor/mcp.json`、`slide-deck/`、`var/` 或既有计划文档改动。

## 自动化验证

执行：

```bash
bash scripts/verify-plan-076.sh
```

结果：

- PLAN-076 pipeline/API/rollout/持久层/语料契约总门禁：**42 passed**；
- 角色/持久层专项回归：**12 passed**（含 membership 晋升与不降权）；
- 前端测试、type-check、production build：**PASS**；
- 部署后的 `/next/workbench` 引用 `index-BuOvl4v-.js`，服务端静态内容可检出 `AD 内部测试版`；
- `GET http://127.0.0.1:8010/api/v1/health`：**HTTP 200，db=ok**；
- 本机 qyunslation 与 pdf2zh 进程分别监听 `127.0.0.1:8010` / `127.0.0.1:7860`；`qyunslation-office.service` 与 `pdf2zh.service` 当前均为 **active**；
- Chromium：`/home/dev/.local/bin/chromium` 可执行；
- 总门禁：**BLOCKED**，不是代码失败。

## 受控部署

已执行既有发布入口：

```bash
bash scripts/deploy-translate-stack.sh
```

结果：

- 部署提交：`09db35f`；
- Alembic migration：**aligned**；
- 前端静态包：**fresh**；
- sidecar 指纹：本地/运行中均为 `7542777de0fd`；
- API 路由探测：`affiliation-segments` / `apply-corrections` → **401**（已注册且鉴权生效）；
- 两个服务重启后：**active**；
- `/api/v1/health`：**HTTP 200，db=ok**。

这证明最新提交已经加载到运行进程，但不等于 AD 领域质量门禁已经通过。

## 阻塞项

评估器 `scripts/plan076-ad-eval.py --direction both` 当前报告：

- `en-zh`：0 cases / 0 source chars / 0 challenge segments；
- `zh-en`：0 cases / 0 source chars / 0 challenge segments。
- 语料合同：`manifest_missing`，因此不会把未登记文件计入分母。

`tests/gold/ad/` 只提交了语料格式和授权规则，没有伪造文献、临床研究文档或重复样本。需由业务/医学专家提供每方向至少 12 份真实授权样本、累计至少 20,000 **源文计量单位**（拉丁词元 + CJK 字符，见 PLAN-076 README）和 100 个 **annotation 挑战片段**，随后补齐机器基线、专家参考译文并重跑评估。

正式浏览器 DevTools MCP 在当前会话不可用；已用本机 Chromium 做入口烟雾截图（非正式 DevTools 证据）：

- `var/plan076-browser/workbench-320.png`
- `var/plan076-browser/workbench-768.png`
- `var/plan076-browser/workbench-1024.png`
- `var/plan076-browser/workbench-1440.png`

截图验证的是 SSO 入口和响应式布局，尚未验证登录后的 AD 选择器、上传、运行详情、术语闭环和下载闭环。
部署重启后复核截图位于 `var/plan076-browser-postdeploy/workbench-{320,768,1024,1440}.png`。

已补充真实 OIDC 登录证据：

- `test01@qyunslation.com`：OIDC callback、BFF session、`/api/v1/me=200`、tenant=`pilot`、`workbench_v2=true`，有效角色为 translator/member；
- `test02@qyunslation.com`：同样完成登录，主机侧 term_admin 授权后 `/api/v1/me=200`、`can_review=true`、`can_manage_terms=true`；
- 登录后的 AD 工作台四视宽截图：`var/plan076-browser-auth/workbench-{320,768,1024,1440}.png`；
- term_admin 登录工作台截图：`var/plan076-browser-auth-term-admin/workbench-1440.png`。

本组截图由临时 Chromium profile 通过 Chrome DevTools Protocol 采集；未保存 token、密码或 session 文件到仓库。

## 测试用户与生产边界

已在受保护 Authentik API 中创建两个 pilot 租户测试账号，并加入非 superuser 的 `qyunslation-vue-beta` 组。账号密码未写入 Git、日志或证据文件；test02 的 term_admin 通过既有主机侧授权脚本授予并记录审计。生产仍保持 OIDC BFF，开发旁路关闭；AD 生产模式仍需在真实语料和专家门禁通过后才可配置为 pilot。
验收结束后已撤销本次产生的 6 个 BFF session，账号保留但当前无活动登录会话。

## Cursor 续接入口

交接基线为 `main@196ba5c`；本交接说明提交并推送后，以 `origin/main` 最新提交为唯一续接入口。开始工作前执行：

```bash
git switch main
git pull --ff-only origin main
git status --short --branch
```

预期只有用户本机未跟踪目录或配置，例如 `.cursor/mcp.json`、`slide-deck/`、`var/`；这些内容不属于 PLAN-076 交付，不应批量加入提交。

已完成骨架，且 [076i](../plans/PLAN-076-ad-bilingual-prompt-quality-system/PLAN-076i-gap-remediation.md) 已部署于 `c0b5a8b`（勿重复造轮子）：

- AD 提示词编译、术语注入、确定性/语义 QA 库、API/UI 接线、pilot allowlist、语料 manifest/schema；
- 前端 build、部署与健康检查；UI 标记 `AD 内部测试版`。

仍需继续的工作严格按以下顺序进行：

0. 076i 工程项已部署。外部证据未过门，见文末「2026-10-02 外部证据」。不要把模拟评审当成专家签署。
1. 由业务/医学负责人提供经过授权和脱敏的真实 AD 中英双向语料，并设置 `PLAN076_AD_CORPUS_ROOT`；禁止使用合成、占位或未批准文件充数。
2. 先验证语料合同：

   ```bash
   PLAN076_AD_CORPUS_ROOT=/secure/plan076/ad \
     .venv/bin/python scripts/plan076-ad-eval.py --direction both --check-corpus
   ```

3. 使用获批的内部 OpenAI-compatible endpoint 生成不可覆盖的 generic baseline 与 AD candidate；公网端点默认 fail-closed：

   ```bash
   PLAN076_AD_CORPUS_ROOT=/secure/plan076/ad \
     .venv/bin/python scripts/plan076-ad-eval.py \
       --direction both --run-model both \
       --base-url http://internal-gateway:11434/v1 \
       --model <approved-model>
   ```

4. 完成四个单元格各至少 5 个任务的 20 任务 pilot，并提交符合 `tests/gold/ad/pilot-report.schema.json` 的报告。
5. 完成 AD 医学专家与中英医学翻译专家双盲评审，并提交符合 `tests/gold/ad/expert-review.schema.json` 的聚合报告。
6. 补齐正式 DevTools 登录后四场景证据、下载权限闭环和回滚演练；所有门禁通过并经明确批准后，才可从 `off` 切到租户 allowlist 的 `pilot`。

执行 `bash scripts/verify-plan-076.sh` 时，如果未挂载授权语料，最终结果预期为 **BLOCKED**；这表示外部证据缺失，不表示代码测试失败。不得把 BLOCKED 改写成 PASS，也不得自动切换为默认生产模式。

## 2026-10-02 外部证据

076i 代码与前端静态资源已随 `c0b5a8b` 部署。`QYUNSLATION_AD_PROMPT_MODE` 未设置，运行时等价于 `off`。语料在 `var/plan076-ad-corpus/`（24 例，Europe PMC / NCBI OA 全文，参考译文是内部模型草稿，不入库）。

| 门禁 | 结果 |
| --- | --- |
| 语料体量 | 通过。en-zh 25475 / zh-en 22939 源文单位；挑战片段 171 / 103 |
| 参考译文硬门 | FAIL。术语召回 0.7355，高风险召回 0.8354，漂移阻断 32 |
| `--run-model both` | 两侧各 24 例均 FAIL（baseline QA 阻断 41，candidate 43）。均分 0.8147 → 0.8064，差 −0.83 个百分点。对比 BLOCKED：`model_run_incomplete` |
| DeepSeek 双角色模拟 | FAIL。24 例，critical 3，kappa 0.122，candidate 偏好 0.3333。文件 `var/plan076-ad-corpus/expert-review.simulation.json`，`simulation: true` |

不得把上述模拟写成专家签署，也不得据此把 AD 切到 `pilot`。

## 上线判定

076i 工程项已部署。上线仍需要：参考译文硬门通过、baseline/candidate 均为 PASS 且达到分差、真人双盲专家验收、pilot soak、DevTools 证据与回滚演练（`scripts/plan076-rollback-drill.sh`）。
