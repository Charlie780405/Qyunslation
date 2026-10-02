# WT-076：AD 中英双向专业翻译发布证据

> 对应计划：[PLAN-076](../plans/PLAN-076-ad-bilingual-prompt-quality-system/README.md)
> 当前状态：**代码与自动化门禁就绪；真实语料、专家验收和正式浏览器 DevTools 证据仍未闭环，暂不宣称完整上线**

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

不包含用户本机的 `.cursor/mcp.json`、`slide-deck/`、`var/` 或既有计划文档改动。

## 自动化验证

执行：

```bash
bash scripts/verify-plan-076.sh
```

结果：

- PLAN-076 pipeline/API/rollout/持久层/语料契约总门禁：**37 passed**；
- 角色/持久层专项回归：**12 passed**（含 membership 晋升与不降权）；
- 前端测试、type-check、production build：**PASS**；
- `GET http://127.0.0.1:8010/api/v1/health`：**HTTP 200，db=ok**；
- 本机 qyunslation 与 pdf2zh 进程分别监听 `127.0.0.1:8010` / `127.0.0.1:7860`；本环境未暴露对应 systemd unit，故不把 `systemctl` 状态作为运行证据；
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

`tests/gold/ad/` 只提交了语料格式和授权规则，没有伪造文献、临床研究文档或重复样本。需由业务/医学专家提供每方向至少 12 份真实授权样本、累计至少 20,000 源字符和 100 个挑战片段，随后补齐机器基线、专家参考译文并重跑评估。

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

## 上线判定

当前可称为“PLAN-076 代码实现和自动化门禁就绪”，不可称为“AD 专业翻译完整功能成功上线”。完成上线还需：真实双向语料评估通过、医学专家签署术语/译文验收、正式 DevTools 四尺寸证据、OIDC 角色矩阵验收，以及按既有发布脚本完成代码部署和回滚演练。
