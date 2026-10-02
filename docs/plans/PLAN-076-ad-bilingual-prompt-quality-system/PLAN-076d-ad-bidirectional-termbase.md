# PLAN-076d：AD 概念词库与双向术语 policy

> 状态：**部分实施（076i G-008：概念表 SSOT 替代机械反转）**
> 父计划：[PLAN-076](./README.md)
> 依赖：[076a](./PLAN-076a-evaluation-contract-corpus.md)

## 目标

把现有单向、扁平、自免范围过宽的 CSV 种子升级为 AD 概念级双向资产。中译英不能通过机械反转英译中 CSV 实现；歧义词、禁用词和不同文档语体必须显式治理。

## 概念种子格式

新增 `glossaries/domain-ad-concepts.csv`，字段冻结为：

```text
concept_key,term_en,term_zh,aliases_en,aliases_zh,
forbidden_en,forbidden_zh,term_type,ambiguity,
applies_to_profiles,status,source_note
```

- `aliases_*`、`forbidden_*` 使用 JSON 数组字符串，禁止自定义分隔符。
- `status` 仅 `curated|candidate|deprecated`；只有 curated 可进入 hard policy。
- `source_note` 记录公司批准、公开权威来源或历史裁决依据，不保存秘密或个人信息。

## 任务

### Task 1：建立 AD 分类与种子准入规则

覆盖：疾病/分型、症状体征、药物/商品名、靶点/通路、细胞/生物标志物、量表/终点、剂量/制剂、安全性、临床设计/统计和 AD 常用专业表达。

**验收标准：**

- [ ] 所有 076a 高风险 annotation 都能映射到一个 concept 或有明确排除理由。
- [ ] AD 以外疾病默认不进入 `domain-ad`，除非是 AD 文档中的比较/共病必需词。
- [ ] 每条 curated concept 至少有中英文首选词和来源说明。

**验证：**

```bash
uv run pytest tests/glossary/test_plan076_ad_seed.py -q
```

**依赖：** 076a annotations
**预计规模：** M（seed、validator、tests，3–4 文件）

### Task 2：导入 Concept SSOT 并保持幂等

导入器按 `concept_key` upsert Concept/ConceptTerm/forbidden，不按词面创建重复 concept；重复运行不增加行数，不覆盖人工更新的更高版本。

**验收标准：**

- [ ] 连续导入两次数据库结果一致。
- [ ] 旧 `domain-autoimmune` 不删除；相同 concept 以 `domain-ad` 的显式优先级解析。
- [ ] deprecated/candidate 不进入运行时 hard glossary。

**验证：**

```bash
uv run pytest tests/persist/test_plan076_ad_import.py -q
```

**依赖：** Task 1
**预计规模：** M（importer、resolver priority、tests，3–5 文件）

### Task 3：修复方向感知的术语注入与快照

`build_run_glossary_path`、`build_term_snapshot` 和译后术语检查统一从任务 direction 解析 `src_lang/tgt_lang`，禁止依赖默认参数。

**验收标准：**

- [ ] 同一 concept 在 en-zh 输出中文首选词，在 zh-en 输出英文首选词。
- [ ] cache key 包含方向、termbase version、source hash 和 domain profile。
- [ ] 任务 snapshot 明确记录双向 policy，不出现 en-zh 快照复用于 zh-en。

**验证：**

```bash
uv run pytest tests/glossary/test_plan076_bidirectional_policy.py \
  tests/pipeline/test_plan076_term_snapshot.py -q
```

**依赖：** Task 2
**预计规模：** M（term inject、snapshot、tests，3–5 文件）

### Task 4：歧义缩写与 AD 领域锚点

AD 模式启动前要求源文至少命中一个高置信锚点：`atopic dermatitis/特应性皮炎`、已批准 AD 药物、核心量表或靶点组合。孤立 `AD` 不算锚点。

歧义 term 设置 `ambiguity=context_required`；只有同段出现全称或多个 AD 锚点时才升级为 hard constraint，否则作为 QA warning。

**验收标准：**

- [ ] “AD” 可区分特应性皮炎与其他常见含义，孤立出现不自动翻译。
- [ ] 无 AD 锚点的文档创建任务返回 `AD_DOMAIN_EVIDENCE_MISSING`。
- [ ] 用户可改选 `general` 重新创建，系统不静默降级。

**验证：**

```bash
uv run pytest tests/glossary/test_plan076_ambiguity.py \
  tests/api/test_plan076_domain_evidence.py -q
```

**依赖：** Tasks 2–3
**预计规模：** M（resolver、preflight validator、tests，3–5 文件）

## Checkpoint 076d

- [ ] 两个方向的高风险 concept 覆盖率 100%。
- [ ] `AD`、`AE`、`IGA` 等歧义/缩写不会被盲目反转。
- [ ] 双向 policy、glossary 和 QA 使用同一 Concept SSOT。

## 不做

- 不用自动翻译批量生成 curated 英文术语。
- 不删除 `domain-autoimmune.csv`。
- 不把术语候选自动批准入库。
