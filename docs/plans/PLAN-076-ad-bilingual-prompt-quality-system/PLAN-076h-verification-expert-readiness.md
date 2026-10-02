# PLAN-076h：汇总验证、内部试运行与专家验证准备

> 状态：**待实施**
> 父计划：[PLAN-076](./README.md)
> 依赖：[076a](./PLAN-076a-evaluation-contract-corpus.md)–[076g](./PLAN-076g-api-ui-rollout.md)

## 目标

用一个诚实的 PASS/FAIL/BLOCKED 汇总门收束 PLAN-076，并把自动评测 MVP 与后续双专家盲审清晰分开。自动门通过只能发布「AD 内部测试版」。

## 任务

### Task 1：实现 verify-plan-076

汇总脚本依次执行：

1. prompt registry/contract；
2. AD seed/import/双向 policy；
3. PDF/Office runtime prompt；
4. deterministic/semantic QA 与 repair；
5. API/frontend；
6. corpus 完整性与双向评测；
7. 性能预算；
8. PLAN-075 非回归。

返回语义：代码 0=PASS，1=FAIL，2=BLOCKED。缺真实语料、模型或浏览器证据属于 BLOCKED；代码/测试失败属于 FAIL，禁止混淆。

**验收标准：**

- [ ] 每个 gate 输出名称、状态、证据路径和简短原因。
- [ ] 任一方向失败时总状态 FAIL。
- [ ] 不能用参考译文或缓存旧报告伪造本次机器结果。

**验证：**

```bash
bash scripts/verify-plan-076.sh
```

**依赖：** 076a–076g
**预计规模：** M（verify、fixtures、tests，3–5 文件）

### Task 2：浏览器与真实文档证据

至少完成四条真实流程：en-zh 文献、en-zh 临床、zh-en 文献、zh-en 临床。每条流程保存预检、运行详情、QA、审核批准和正式产物证据。

**验收标准：**

- [ ] UI 显示正确方向、domain/profile、prompt/termbase version。
- [ ] 人为制造一个 blocker 时正式下载被拒绝；修复并批准后才可下载。
- [ ] 刷新、服务重启和任务恢复不改变 generation snapshot。

**验证：** 真实 Chrome DevTools 流程；证据写入 `docs/evidence/plan076/`，结论写入 WT-076。

**依赖：** 076g
**预计规模：** M（浏览器脚本、证据索引、WT，3–5 文件；截图不计）

### Task 3：20 个任务 pilot soak

在 allowlist 租户运行至少 20 个真实 AD 任务，两个方向和两类文档均不少于 5 个。记录 blocker、warning、误报、修复回滚、人工批准、耗时和 token。

**验收标准：**

- [ ] 高风险事实错误为 0，药名漂移为 0。
- [ ] 无无法解释的 prompt/version/termbase 漂移。
- [ ] P95 性能与成本增幅均 ≤25%。
- [ ] 任一关键门失败时维持 pilot，不切 default。

**验证：**

```bash
uv run python scripts/plan076-ad-eval.py --pilot-report var/plan076-pilot
```

**依赖：** Tasks 1–2
**预计规模：** S（reporter 与 WT 证据，1–2 文件）

### Task 4：专家盲审包与升级门

MVP 后生成去模型标识、随机顺序的双盲审包。两名角色分别为 AD 医学专家和中英医学写作/翻译专家；分歧先独立复核，再由约定仲裁人裁决。

**验收标准：**

- [ ] 评分 rubric 固定 critical/major/minor、事实/术语/完整性/语言质量类别。
- [ ] Critical=0、Major≤1/1,000 源文词、κ≥0.70、候选盲选偏好≥70%。
- [ ] 未达到标准时产品继续显示「内部测试版」，不得改为「专家验证」。

**验证：** 盲审结果导入后由 `plan076-ad-eval.py --expert-review` 生成只读报告。

**依赖：** Task 3
**预计规模：** M（rubric、export/import、report，3–5 文件）

## 最终交付

- `scripts/verify-plan-076.sh`
- `docs/walkthroughs/WT-076-ad-bilingual-prompt-quality-system.md`
- `docs/evidence/plan076/`
- `var/plan076-ad-eval/` 与 `var/plan076-pilot/`（不进 Git）
- prompt、termbase、QA、浏览器、pilot 和后续专家评审的相互追溯链

## 完成定义

- 自动门全部 PASS 且 pilot soak 通过：PLAN-076 工程完成，产品可标「AD 内部测试版」。
- 专家盲审缺失：专家验证状态必须 BLOCKED，但不得把已通过的工程项标失败。
- 专家盲审达标：可另行批准产品文案升级，不自动由脚本修改生产文案。

