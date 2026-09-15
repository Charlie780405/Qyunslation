# PLAN-063a：裁决反哺排除规则

> 父计划：[PLAN-063](./README.md)

目标：被否决过的词不再重复进候选队列；高频否决模式能归纳成规则提案，经人工 promote 落入 SSOT。

## 1. `glossaries/term-exclusions.csv`（新增，入 git）

**不复用** `governance.FIELDNAMES`——那是 `source → target` 词条 schema，语义不同。独立 schema：

```csv
source,reason,scope,tenant_slug,project_slug,decided_by,candidate_id,decided_at,occurrences,notes
```

- `scope` 取 `{global, tenant, project}`，控制生效范围。
- 由人工 `reject` / `do_not_translate` 裁决聚合产生。
- [qyunslation/glossary/candidate_rules.py](../../../qyunslation/glossary/candidate_rules.py) 的 `DEFAULT_EXCLUSIONS` 常量已预留并在 `load_rules()` 时并入 denylist，文件至今不存在；本子计划补文件生成与 scope 过滤。
- 首批行由 [PLAN-063e](./PLAN-063e-062-closeout.md) 第 2 节回填：PLAN-062 现场手改进 TOML 的领域歧义词（`TARGET`、`DERM`、`ADA`、`ACAD`、`DERMATOL`、`Inc`、`USA`、`MBA`、`PHARMACEUTICAL`）迁到本 CSV，TOML 只留统计/语法类停用词。

效果：同一个词被否过就不再进队列，这是「不译规则自动进化」的载体。

## 2. alembic 迁移 `063a0001_term_rule_stats.py`

给 `workbench_translation_run` 增加 `excluded_stats JSON`：

```json
{
  "CELL_PRESERVE": 12, "DENYLIST": 3, "FRAGMENT": 2,
  "SCREEN_GENERIC": 9, "SCREEN_NOISE": 7,
  "screen_origin": {"llm": 14, "cap": 0, "error": 0, "disabled": 0},
  "extracted_total": 61, "rules_version": "063-v1"
}
```

`bridge._extract_candidates` 目前把排除原因码只回显在 `_summary`（PLAN-061 的口径），本迁移让它落库，成为规则归纳与台账的数据源。

口径已在 PLAN-062 定稿（删除裸 `abbreviation` / `organization` include 规则，新增 `FRAGMENT` / `SCREEN_GENERIC` / `SCREEN_NOISE`），本迁移一次写对即可。两项必须一并落库，否则 063b 的盲区指标算不出来：

- `screen_origin`：`ScreenVerdict.origin` 目前只在内存（`termbase` / `decisions_csv` / `llm` / `cap` / `disabled` / `error`）。
- `extracted_total`：噪声率与 `screen_generic_ratio` 的分母。

## 3. `scripts/plan063-evolve-term-rules.py`（新增）

```bash
python3 scripts/plan063-evolve-term-rules.py --report              # 只读 DB，产出提案
python3 scripts/plan063-evolve-term-rules.py --promote PROP-003    # 落规则并 bump version
```

`--report` 逻辑：

- 读 `TermDecision`（`reject` / `do_not_translate`）联 `DocumentTermCandidate` 的 `match_type` / `risk` / 出现次数。
- **人工与机器裁决都要读，但权重不同**：`actor_sub` 以 `plan062-purge` / `machine_` 开头的视为机器裁决，单独的机器拒绝**不构成** denylist 提案，须另有人工裁决或跨 ≥2 文档佐证。机器裁决的补记见 [PLAN-063e](./PLAN-063e-062-closeout.md)，本子计划开工前该表必须已补齐，否则 `--report` 对最大一批拒绝证据失明。
- 聚合四类提案：
  1. **denylist 条目**：被否 ≥3 次且跨 ≥2 个文档。
  2. **新 exclude 正则**：多个被否词共享形态时用字符类归纳。
  3. **收录提案**：`glossaries/term-screen-decisions.csv` 中被裁为 `domain_term` ≥N 次、且 Concept 库无 curated 记录的词，提案进 curated CSV。PLAN-062a 的 harvest 提升是人工经 `glossaries/staging/plan062-harvest-promote.csv` 完成的，本条把它变成可复现流程。
  4. **别名 / 形态提案**：`anti-X`、`non-X`、`X-50/75/90` 等变体回填为既有 Concept 的 alias，消化 PLAN-062d 查库不识别词缀变体的缺口。
- 每条正则提案**必须附反向验证**：对保留清单（`tralokinumab`、`IL-13`、`NHS`、`EASI`、`BSA`、`ABC-101`）逐一回放，任一被误杀则该提案直接丢弃并记录原因。
- 提案写 `.cursor/skills/skill-registry/term-rules-inbox.md`。
- `--screen-pending` 见 [PLAN-063e](./PLAN-063e-062-closeout.md) 第 3 节：对历史 pending 批量走三级裁定，出提案不落库。

`--promote` 才落 `term-exclusions.csv` / `term-candidate-rules.toml`，bump `version`，追加 `registry.md` 审计行。

## 4. 版本漂移门禁

PLAN-062 现场手改 TOML `denylist` 而 `version` 仍为 `062-v1`，导致规则内容变了指纹没变，063b 的台账无法按版本对比。

- `--promote` **必须** bump `version`，不接受「只加条目不动版本」。
- `verify-plan-063.sh` 增断言：`term-candidate-rules.toml` 的 `denylist` / `patterns` / `include` 内容哈希与 `version` 绑定登记在 `registry.md`，哈希变而 `version` 未变则 fail（错误签名 `SIG-RULES-VERSION-DRIFT`）。
- 版本断言只留一处 SSOT：测试读 `rules_version()` 与登记表比对，不再在多个测试里硬编码版本字符串。

红线：**只读 DB，不写 DB**。规则变更全部走 git，可 review 可回滚。沿用 SK-Q008 的 capture/promote 范式；人工 promote 是刻意设计的边界，理由写入 ADR-032（误杀成本远高于人工一次 promote 的成本）。
