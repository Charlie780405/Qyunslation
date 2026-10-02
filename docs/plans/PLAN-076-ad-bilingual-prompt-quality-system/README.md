# PLAN-076：AD 中英双向专业翻译质量系统

> 状态：**代码垂直切片已落地；真实语料、专家验收与正式 UI 门禁待完成**
> 日期：2026-10-02
> 依赖：PLAN-051、PLAN-058、PLAN-063、PLAN-071、PLAN-073、PLAN-074、PLAN-075

## 目标

把 Qyunslation 从「通用文档翻译 + 医药术语表」升级为面向药企医学、临床和研发团队的 **AD（特应性皮炎）中英双向专业翻译质量系统**：

- 只支持简体中文 ↔ 英文，两个方向同时设发布门禁；
- MVP 只覆盖 AD，不宣称覆盖全部自免疾病；
- 首批文档类型为医学研究文献和临床研究文档；
- 提示词、术语、模型、QA 和人工批准全程可追溯；
- MVP 先用自动评测进入内部试用，完成双专家盲审后才允许使用「专家验证」表述。

## 已确认基线

1. `segments_agent.py` 与 `markdown_agent.py` 的核心角色仍是通用 machine translation engine，AD 专业性主要来自术语注入。
2. PDF/BabelDOC 已支持 `custom_system_prompt`，但当前 runner 没有按领域、方向和文档类型编译提示词。
3. `term_inject.py` 与 `term_snapshot.py` 默认按 `en → zh` 解析术语，中译英并非真实对称链路。
4. `domain-autoimmune.csv` 只有约 35 个条目，且混有 AD 以外疾病，不能支撑 AD 产品承诺。
5. 现有 10 份自免金标中 9 份是占位文本；唯一机器语料来自双语 PDF，评测器会把英文源文中的药名误计为中文译名漂移。

因此实施顺序必须是：**先建立可信评测，再实现提示词与术语，再增加 QA/修复，最后接 UI 与灰度。**

## 冻结决策

- 提示词是代码资产：Git 评审、版本化、带摘要、可灰度、可回滚；不提供生产提示词在线编辑。
- 使用组合式提示词，不复制六套完整大模板：`base + domain + direction + document + task`。
- BabelDOC 的 `custom_system_prompt` 只承载领域角色和医学语义合同；标签、占位符、JSON 结构仍由上游模板管理。
- 术语通过独立 policy/glossary 通道注入，不把整张词库拼进固定系统提示词。
- 旧客户端不传 `domain_profile` 时保持现有通用行为；新工作台显式提交 `domain_profile=ad`。
- AD 模式缺模板、版本摘要不一致、方向不支持或 QA 降级时必须显式失败/阻断，禁止静默伪装为专业翻译。
- 自动语义 QA 只处理高风险段落；最多定点修复一次，修复后重新跑全部确定性门禁。
- 正式产物继续沿用 PLAN-071 的人工批准门禁，PLAN-076 不允许自动发布。

## 公共契约

### 请求扩展（向后兼容）

`POST /api/v1/translation-runs` 与 `PATCH /api/v1/preflights/{id}` 增加可选字段：

```json
{
  "domain_profile": "ad"
}
```

- 允许值：`general | ad`；缺省为 `general`，避免旧客户端行为漂移。
- `domain_profile=ad` 时仅允许：
  - `direction`: `English → 简体中文` 或 `简体中文 → English`
  - `profile`: `医学研究文献` 或 `临床研究文档`
- 现有 `监管申报材料`、`通用医药文档` 继续走通用提示词，不在本 MVP 内。

### 响应扩展

TranslationRun 增加只读 `prompt_snapshot`：

```json
{
  "profile_id": "ad.en-zh.literature.translate.v1",
  "version": "076-v1",
  "digest": "sha256:...",
  "domain_profile": "ad",
  "direction": "en-zh",
  "document_profile": "医学研究文献",
  "termbase_version": "058-...",
  "compiler_version": "076-compiler-v1"
}
```

普通接口不返回完整系统提示词。完整编译产物仅写入受保护的运行目录和审计证据。

`GET /translation-runs/{id}/qa-items` 保持现有资源路径，在 `evidence` 中增加：`source_span`、`target_span`、`direction`、`prompt_version`、`rule_version`、`repair_attempt`。不新增平行 QA API。

### 错误语义

| 场景 | HTTP/状态 | 代码 |
| --- | --- | --- |
| AD + 不支持方向/文档类型 | 422 | `AD_PROFILE_UNSUPPORTED` |
| 源文没有任何 AD 领域锚点 | 422 | `AD_DOMAIN_EVIDENCE_MISSING` |
| 提示词注册表/摘要损坏 | 503 | `AD_PROMPT_UNAVAILABLE` |
| 语义 QA 服务不可用 | run `qa_degraded` | `AD_QA_DEGRADED` |
| 修复改变受保护事实 | run `qa_blocked` | `AD_REPAIR_FACT_DRIFT` |

## 子计划与依赖

| 子计划 | 目标 | 依赖 | 波次 |
| --- | --- | --- | --- |
| [076a](./PLAN-076a-evaluation-contract-corpus.md) | 评测 v3、真实双向语料与基线 | 无 | 0 |
| [076b](./PLAN-076b-prompt-registry-compiler.md) | 提示词注册表、组合编译与快照 | 076a 契约 | 1 |
| [076c](./PLAN-076c-translation-prompts-runtime.md) | AD 翻译提示词与 PDF/Office 接线 | 076b、076d 契约 | 2 |
| [076d](./PLAN-076d-ad-bidirectional-termbase.md) | AD 概念词库、双向 policy 与领域锚点 | 076a | 1 |
| [076e](./PLAN-076e-bidirectional-deterministic-qa.md) | 双向确定性医学 QA | 076c、076d | 3 |
| [076f](./PLAN-076f-semantic-qa-repair.md) | 风险驱动语义 QA 与一次定点修复 | 076e | 3 |
| [076g](./PLAN-076g-api-ui-rollout.md) | API/UI 可见性、审计和灰度 | 076b–076f | 4 |
| [076h](./PLAN-076h-verification-expert-readiness.md) | 汇总验证、试运行与专家验证准备 | 076a–076g | 5 |

```text
076a ──┬──> 076b ───────┐
       └──> 076d ──┐    │
                   └─> 076c ─> 076e ─> 076f
                                      │
076b ─────────────────────────────────┴─> 076g ─> 076h
```

076b 与 076d 可在 076a 的评测/术语标注契约冻结后并行；076e 与 076f 必须顺序实施，避免语义模型掩盖确定性规则缺陷。

## 建议团队与排期

以下为 **5 人核心团队、8 周内部测试版** 的容量假设，不是对外发布日期：

- 技术负责人/后端 1 人：提示词编译、运行时、QA 编排和技术门禁；
- 全栈工程师 1 人：API、任务快照、工作台和审计可见性；
- 测试/数据工程师 1 人：评测器、回归集、流水线和试运行证据；
- AD 医学专家 0.5 人：领域边界、概念词库、风险片段和医学错误分级；
- 中英医学翻译/写作专家 0.5 人：双向译法、风格合同和盲审量表。

| 周次 | 主交付 | 出口条件 |
| --- | --- | --- |
| 第 1–2 周 | 076a 评测契约、真实语料、通用基线 | 双向数据量达标；旧评测误报已修复 |
| 第 2–3 周 | 076b 提示词编译器与 076d AD 概念词库 | 编译确定性、快照可追溯、双向术语闭环 |
| 第 3–4 周 | 076c 四套 AD 提示词运行时接线 | PDF/Office/Markdown/Segments 行为一致 |
| 第 5 周 | 076e 确定性 QA | 医学事实与结构硬门禁达到目标 |
| 第 6 周 | 076f 语义 QA 与一次定点修复 | 修复不可引入事实漂移；成本/时延达标 |
| 第 7 周 | 076g API/UI、审计与 shadow/pilot 灰度 | 旧客户端无回归；AD 失败语义可见 |
| 第 8 周 | 076h 汇总验证与 20 任务试运行 | 所有自动门禁通过，形成专家盲审包 |

关键路径为 `076a → 076d → 076c → 076e → 076f → 076g → 076h`。若真实语料或专家标注延迟，禁止通过压缩 076a 绕过；应顺延内部试用。正式「专家验证」不计入上述 8 周，需在内部测试稳定后另安排双盲评审窗口。

## 全局发布门槛

自动评测 MVP：

- 每方向至少 12 个真实文档案例、20,000 源文词、100 个挑战片段；
- 两方向术语准确率分别 ≥98%，高风险术语召回 100%，禁用译法与药名漂移为 0；
- 药名、靶点、剂量、单位、数字、统计量、否定、情态和终点保护召回 100%；
- 段落/ID/占位符最终完整率 100%，首轮结构合规率 ≥99.5%；
- 相同模型下，AD 提示词自动综合分比通用提示词至少提高 10 个百分点，任何硬门禁不得退化；
- 风险驱动 QA 后端到端 P95 耗时和 token 成本增幅均不超过 25%；
- 现有 PLAN-075 回归与 PLAN-076 汇总验证均无 FAIL。

专家验证（MVP 后）：

- AD 医学专家与中英医学写作/翻译专家双人盲审；
- Critical error = 0，Major error ≤1/1,000 源文词；
- Cohen's κ ≥0.70，候选方案相对通用基线盲选偏好率 ≥70%。

专家门未完成前，只能标记「AD 内部测试版」，不能标记「专家验证」。

## 不做

- 不扩展其他自免疾病、其他语言或繁体中文。
- 不做模型微调、医学知识 RAG、自动医学写作或无人审核发布。
- 不在本计划重做 PDF/Office 版式引擎。
- 不删除历史 `domain-autoimmune` 资产；完成迁移验证前仅新增 `domain-ad` 概念层。
- 不用 LLM-as-a-judge 的单一分数替代确定性事实门禁或后续专家盲审。

## 计划级验证

```bash
uv run pytest tests/prompts tests/glossary tests/pipeline tests/api -q
uv run python scripts/plan076-ad-eval.py --direction both --baseline generic --candidate ad-v1
cd frontend && npm test && npm run type-check && npm run build
bash scripts/verify-plan-075.sh
bash scripts/verify-plan-076.sh
```
