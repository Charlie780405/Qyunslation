# PLAN-076a：评测真值、双向语料与基线

> 状态：**待实施**
> 父计划：[PLAN-076](./README.md)
> 依赖：无

## 目标

先建立不会被双语 PDF、占位语料和无关共享术语污染的 AD 双向评测。076a 是后续提示词、术语和 QA 的唯一发布真值；没有 076a PASS，不允许用自动分数评价提示词优劣。

## 评测契约

新增 `tests/gold/ad/manifest.schema.json` 和受控语料 manifest。每个 case 至少包含：

```json
{
  "case_id": "ad-en-zh-001",
  "direction": "en-zh",
  "document_profile": "医学研究文献",
  "source_ref": "source.txt",
  "reference_ref": "reference.zh.txt",
  "source_sha256": "...",
  "reference_sha256": "...",
  "annotations_ref": "annotations.json",
  "license": "public-or-internal-approved",
  "is_locked_test": true
}
```

`annotations.json` 按源文证据标注概念和事实，不再使用所有样本共享的字面必中词：

- `concept_id`、源文 span、期望目标概念/允许别名；
- fact 类型：drug、target、endpoint、dose、unit、number、statistic、negation、modality、study_id；
- `criticality`: high/medium/low；
- 仅当源文存在该概念或事实时才计入分母。

内部文档默认放在受控的 `PLAN076_AD_CORPUS_ROOT`，不进入 Git；仓库只保存脱敏的小型 fixture、manifest 和哈希。公开且许可证允许的短文本可作为测试 fixture 提交。

## 任务

### Task 1：实现单语目标提取与输入完整性检查

**描述：** 新建 PLAN-076 评测器，不复用 PLAN-073 的双语全文拼接计分方式。机器输出必须是单语目标文本；若输入同时包含大段源语言和目标语言，case 标记 `invalid_corpus`，不得继续算术语准确率。

**验收标准：**

- [ ] 双语 PDF 中英文 `dupilumab` 不再产生中文药名漂移。
- [ ] 缺 source/reference/annotation、哈希不匹配或文本过短时明确 FAIL/BLOCKED。
- [ ] 评测器不会回写源语料、参考译文或机器输出。

**验证：**

```bash
uv run pytest tests/gold/test_plan076_eval_contract.py -q
```

**依赖：** 无
**预计规模：** M（评测脚本、schema、测试 fixture，3–5 文件）

### Task 2：实现方向感知的概念与事实评分

**描述：** 按 `direction` 选择允许目标词、禁用词和源/目标语言残留规则；分别计算术语准确率、事实保护率、完整性、结构合规率和漂移数。

自动综合分冻结为：术语 35%、受保护事实 35%、内容完整性 20%、结构合规 10%。任一 hard gate 失败时，综合分只用于诊断，不得把 case 判 PASS。

**验收标准：**

- [ ] `en-zh` 和 `zh-en` 分开汇总，不能用平均值掩盖单方向失败。
- [ ] 允许别名按 concept 匹配，禁止仅用不区分边界的 substring 计分。
- [ ] 报告记录模型、prompt、termbase、compiler、语料 manifest 摘要。

**验证：**

```bash
uv run pytest tests/gold/test_plan076_bidirectional_scoring.py -q
```

**依赖：** Task 1
**预计规模：** M（评分器与测试，3–4 文件）

### Task 3：建立真实 AD 双向语料台账

**描述：** 每方向至少纳入 12 个真实文档案例：医学研究文献 6 个、临床研究文档 6 个；每方向累计不少于 20,000 源文词，并从真实文档中抽取至少 100 个挑战片段。

**验收标准：**

- [ ] 现有 9 个 `Dupilumab for AD.` 占位样本不进入 PLAN-076 分母。
- [ ] 开发集与锁定测试集按 case 隔离，锁定集 manifest 有稳定哈希。
- [ ] 语料授权、脱敏状态、方向、文档类型和来源均可审计。

**验证：**

```bash
uv run python scripts/plan076-ad-eval.py --check-corpus --direction both
```

**依赖：** Task 1
**预计规模：** M（manifest、台账与检查器；真实语料本体不计入代码文件）

### Task 4：冻结通用提示词基线

**描述：** 用相同模型、temperature、并发、词库和输入分别运行当前通用提示词，生成不可覆盖的 baseline report；后续候选只允许改变 prompt profile，不得混入模型升级造成假提升。

**验收标准：**

- [ ] baseline/candidate 的模型、参数、语料和术语库摘要完全一致。
- [ ] 每个 case 可追溯到机器输出与运行日志。
- [ ] 重跑不会覆盖历史 baseline，报告使用 run ID 和时间戳区分。

**验证：**

```bash
uv run python scripts/plan076-ad-eval.py --direction both --baseline-only
```

**依赖：** Tasks 2–3
**预计规模：** S（脚本参数与报告写入，1–2 文件）

## Checkpoint 076a

- [ ] 每方向真实语料数量、词数和挑战片段数量达标。
- [ ] `invalid_corpus`、BLOCKED 和 FAIL 三态可信。
- [ ] baseline 报告不含双语源文污染。
- [ ] 人工抽查 10 个 annotation，所有分母均能定位到源文 span。

## 不做

- 不在本阶段优化提示词或词库。
- 不把参考译文当机器译文填补缺失结果。
- 不用 BLEU/ROUGE 单独决定医学翻译是否通过。
