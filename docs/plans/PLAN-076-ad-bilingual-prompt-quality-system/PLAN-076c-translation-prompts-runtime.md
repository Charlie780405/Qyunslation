# PLAN-076c：AD 双向翻译提示词与运行时接线

> 状态：**待实施**
> 父计划：[PLAN-076](./README.md)
> 依赖：[076b](./PLAN-076b-prompt-registry-compiler.md)、[076d](./PLAN-076d-ad-bidirectional-termbase.md) 的 policy 接口

## 目标

实现 AD 文献/临床资料的中英双向提示词，并让 PDF、DOCX、PPTX 实际使用同一领域语义合同；不复制或覆盖 BabelDOC 已有的标签、占位符和 JSON 结构规则。

## 冻结提示词合同

基础角色：

```text
/no_think
You are a bilingual medical translator specializing in atopic dermatitis
literature and clinical-development documents.

Priority:
1. Preserve medical meaning and every factual relationship.
2. Preserve drugs, targets, endpoints, numbers, units, statistics,
   negation, uncertainty and regulatory force exactly.
3. Apply every approved glossary constraint.
4. Produce natural professional text in the target language.

Never summarize, omit, add, explain, infer, or silently resolve ambiguity.
Do not strengthen or weaken causality, efficacy, safety, recommendation,
obligation, probability, or statistical conclusions.
Do not invent abbreviation expansions or normalize facts absent from source.
Return translation only.
```

方向规则：

- `en-zh`：规范简体中文医学表达；批准中文药名/适应症名优先；INN、商品名、符号、缩写关系不得改变。
- `zh-en`：国际医学英语；不得弱化/强化“可能、提示、相关、显著、应、须、不得”等语义；不凭常识增加主语、适应症或因果关系。

文档规则：

- 文献：保护作者、期刊、DOI、引用编号、图表编号；研究结论保持原证据强度。
- 临床：保护剂量、给药频率、访视窗、入排标准、终点、分析集、不良事件、方案编号和盲法/随机化关系。

## 任务

### Task 1：实现四个 translation profile

**验收标准：**

- [ ] 每个 profile 都包含基础、AD、方向和文档模块，且不重复上游结构指令。
- [ ] `AD` 缩写只由术语 policy 在有局部证据时硬约束，固定 prompt 不直接声明所有 `AD` 都是 atopic dermatitis。
- [ ] 作者名、DOI、URL、研究编号和占位符在 prompt contract 中明确不可臆改。

**验证：**

```bash
uv run pytest tests/prompts/test_plan076_translation_profiles.py -q
```

**依赖：** 076b
**预计规模：** M（方向/文档模板与合同测试，4–5 文件）

### Task 2：接入 PDF/BabelDOC runtime config

在现有 per-run `runner-config.toml` 生成阶段写入 `translation.custom_system_prompt`；启动前探测当前 pdf2zh/BabelDOC 是否支持该字段。glossary 继续走 `--glossaries`，不得重复拼接到 system prompt。

**验收标准：**

- [ ] runner config 中 prompt 与 snapshot digest 一致。
- [ ] AD prompt 不修改全局 `/home/dev/pdf2zh/config.toml`。
- [ ] capability probe 失败时返回 `AD_PROMPT_UNAVAILABLE`，不启动通用翻译冒充 AD。

**验证：**

```bash
uv run pytest tests/workbench/test_plan076_pdf_prompt_runtime.py -q
```

**依赖：** Task 1
**预计规模：** M（runtime config、runner、tests，3–5 文件）

### Task 3：接入 Office/Markdown/Segments agents

将 compiled domain prompt 作为受控 system extension 传给现有 agent；API/用户传入的 `custom_prompt` 在 AD 模式下不得覆盖生产合同。通用模式维持旧行为以兼容现有用户。

**验收标准：**

- [ ] DOCX/PPTX/PDF 同一 case 使用相同 profile/version/digest 语义。
- [ ] AD 模式下自由 custom prompt 被拒绝并返回 422，而不是悄悄忽略。
- [ ] 通用模式现有 custom prompt 测试保持通过。

**验证：**

```bash
uv run pytest tests/translator/test_plan076_agent_prompt_runtime.py \
  tests/api/test_plan076_prompt_boundary.py -q
```

**依赖：** Tasks 1–2
**预计规模：** M（agent factory、configs、API boundary tests，4–5 文件）

### Task 4：同模型 A/B 回放

使用 076a 锁定语料，保持模型、参数、词库一致，只比较 generic 与 AD prompt。输出 case 级差异和失败类型，不允许只报总平均。

**验收标准：**

- [ ] 两方向分别生成 baseline/candidate 报告。
- [ ] 任一 hard gate 回退时候选判 FAIL，即使综合分上升。
- [ ] 报告可定位到 prompt digest 和机器输出。

**验证：**

```bash
uv run python scripts/plan076-ad-eval.py --direction both --baseline generic --candidate ad-v1 --run-model both
```

**依赖：** Tasks 2–3、076a、076d
**预计规模：** S（评测适配与证据，1–2 文件）

## Checkpoint 076c

- [ ] PDF、DOCX、PPTX 至少各有一份双向 smoke case。
- [ ] 运行日志、prompt snapshot、termbase snapshot 相互一致。
- [ ] AD 模式无法被自由 prompt 绕过。

## 不做

- 不改 BabelDOC 的结构模板和排版算法。
- 不让系统提示词承担术语检索或事实 QA。
- 不在本阶段自动修复译文。
