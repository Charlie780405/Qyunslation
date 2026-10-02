# PLAN-076e：AD 中英双向确定性 QA

> 状态：**部分实施（076i G-004/G-105：全格式 QA 与中文数字规则）**
> 父计划：[PLAN-076](./README.md)
> 依赖：[076c](./PLAN-076c-translation-prompts-runtime.md)、[076d](./PLAN-076d-ad-bidirectional-termbase.md)

## 目标

把现有以中文目标为主的 QA 扩展为真正双向的医学事实门禁。确定性规则是发布真值；语义 QA 只能补充，不能覆盖或降低确定性 blocker。

## QA 类型与严重度

| 类别 | 示例 | 默认严重度 |
| --- | --- | --- |
| 药物/靶点/终点 | 药名漂移、靶点符号变化、主要终点遗漏 | blocker |
| 数字与统计 | 剂量、单位、百分比、P 值、CI、样本量变化 | blocker |
| 否定与情态 | not/无/未、may/可能、must/必须方向变化 | blocker |
| 研究实体 | 方案号、NCT/IND、访视窗、组别错位 | blocker |
| 术语 | 高风险批准译名缺失、禁用译法 | blocker；普通术语 warning |
| 内容残留 | 目标中文仍有大段英文；目标英文仍有大段中文 | warning/blocker 按比例 |
| 结构/元数据 | ID、占位符、作者、DOI、URL、引用编号 | blocker |

## 任务

### Task 1：统一双向 QA Context

新增方向显式的 `QaContext`，所有规则必须接收 direction、document profile、term snapshot 和 source/target spans；禁止通过“目标文本是否含中文”猜方向。

**验收标准：**

- [ ] 旧 en-zh 调用适配到显式 context，结果不退化。
- [ ] zh-en 有独立的中文残留和英文目标规则。
- [ ] finding evidence 始终包含 direction 和 rule_version。

**验证：**

```bash
uv run pytest tests/pipeline/qa/test_plan076_context.py -q
```

**依赖：** 076c–076d
**预计规模：** M（QA types、adapter、tests，3–5 文件）

### Task 2：事实与统计保护规则

源文和译文先抽取规范化事实 token，再比较概念和值，不直接比较整段字符串。覆盖中文/英文数字、全半角、范围、±、百分比、单位、P 值、CI、给药频率和访视窗。

**验收标准：**

- [ ] `300 mg Q2W`、`300 mg 每2周一次` 在双向可判等价。
- [ ] 300→30、mg→μg、95% CI 数值变化均产生 blocker。
- [ ] 允许标点/空格/大小写规范化，不允许值或单位被吞掉。

**验证：**

```bash
uv run pytest tests/pipeline/qa/test_plan076_facts_statistics.py -q
```

**依赖：** Task 1
**预计规模：** M（extractors、rules、tests，4–5 文件）

### Task 3：否定、情态和比较方向规则

识别 `not/no/without/未/无/不`、`may/might/可能/提示`、`must/shall/须/必须/不得` 及 increase/decrease、superior/inferior 等方向词。规则只在有可对齐 span 时下 blocker；无法对齐时留给 076f。

**验收标准：**

- [ ] 否定丢失、must→may、升高→降低产生 blocker。
- [ ] 同义但强度等价的表达不误报。
- [ ] 无 span 证据时不生成伪精确 blocker。

**验证：**

```bash
uv run pytest tests/pipeline/qa/test_plan076_negation_modality.py -q
```

**依赖：** Task 1
**预计规模：** M（rules、fixtures、tests，3–5 文件）

### Task 4：术语、残留和结构整合

把双向 term snapshot、现有 protected literal、作者/参考文献和结构检查汇总为统一 QA report。中英残留阈值按方向配置；批准保留的英文缩写、药名和符号从残留分母剔除。

**验收标准：**

- [ ] 高风险术语检查使用方向正确的 preferred/forbidden target。
- [ ] 合法 IL-4Rα、EASI、DLQI 不触发英文残留。
- [ ] QA blocker 继续阻止现有 review approval/formal export。

**验证：**

```bash
uv run pytest tests/pipeline/qa/test_plan076_term_residue_structure.py \
  tests/api/test_plan076_formal_gate.py -q
```

**依赖：** Tasks 2–3
**预计规模：** M（integration、tests，3–5 文件）

## Checkpoint 076e

- [ ] 每类规则至少有正例、错误例和等价表达例。
- [ ] 每方向高风险事实保护召回 100%。
- [ ] 确定性 blocker 无法被 reviewer note 或语义模型降级。

## 不做

- 不使用语言模型判断纯数字/单位是否一致。
- 不在规则无法定位证据时猜测错误。
- 不自动修改译文。
