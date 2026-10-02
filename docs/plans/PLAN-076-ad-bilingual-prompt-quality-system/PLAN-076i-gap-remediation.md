# PLAN-076i：工程缺口收敛台账

> 状态：**实施中**
> 父计划：[PLAN-076](./README.md)
> 来源：深度审查（WT-076 + 代码对照）2026-10-02

## 目标

在挂载真实语料之前，关闭会让「AD 内部测试版」质量声明不可信的 P0 工程缺口，并收敛 P1 契约/运维项。外部语料与专家门仍按 076a/076h 顺序进行，**不得**用合成语料绕过。

## P0 缺口台账

| ID | 严重度 | 证据 | 修复项 | 验收测试 |
| --- | --- | --- | --- | --- |
| G-001 | P0 | `executors/legacy.py:32` Office 未传 AD prompt | v2 Office/Image 透传 `domain_profile`/`ad_prompt_text` | `test_plan076_office_prompt.py` |
| G-002 | P0 | `ad_runtime.py:29-30` shadow 等同全开放 | shadow 拒绝创建；废弃 default→off | `test_plan076_rollout_modes.py` |
| G-003 | P0 | `v1.py:1737` 启动重编译无 digest 校验 | 创建时冻结 `compiled-system.txt`；启动比对 digest | `test_plan076_prompt_freeze.py` |
| G-004 | P0 | `v1.py:1214` 无 PDF 跳过 AD QA | 全格式文本抽取；不可抽取→blocker | `test_plan076_ad_qa_formats.py` |
| G-005 | P0 | `v1.py:1270` 语义 QA 仅计数 | 编排 reviewer/超时/一次修复/重跑确定性 QA | `test_plan076_semantic_pipeline.py` |
| G-006 | P0 | `plan076-ad-eval.py:832` 挑战片段按 case 计 | 按 annotation 条目计数；统一 `_source_units` | `test_plan076_eval.py` |
| G-007 | P0 | 评测无 98%/100% 硬门 | 分层硬门；空分母 BLOCKED；Wilson CI | `test_plan076_eval.py` |
| G-008 | P0 | `ad_termbase.py:31-42` zh-en 机械反转 | `domain-ad-concepts.csv` 概念 SSOT | `test_plan076_ad_termbase.py` |
| G-009 | P0 | `verify-plan-076.sh` 未串 075 | 汇总门禁调用 `verify-plan-075.sh` | 脚本 exit 0/2 |

## P1 缺口台账

| ID | 严重度 | 证据 | 修复项 | 验收测试 |
| --- | --- | --- | --- | --- |
| G-101 | P1 | `ad_runtime.py:63` 拼接 custom_prompt | AD 模式 422 拒绝 | `test_plan076_ad_runtime.py` |
| G-102 | P1 | allowlist 404 / prompt 422 | HTTP 422/503 与契约对齐 | `test_plan076_ad_contract.py` |
| G-103 | P1 | 幂等键不含 domain_profile | hash 含 profile | `test_plan076_ad_contract.py` |
| G-104 | P1 | snapshot 缺 model/termbase/QA 版本 | 创建时写入完整 snapshot | `test_plan076_ad_prompt.py` |
| G-105 | P1 | `ad_qa.py` ASCII 数字 | 全角/万/亿/≥/μg；否定「非」 | `test_plan076_ad_qa.py` |
| G-106 | P1 | 前端全员可见 AD | `/me` `ad_enabled` 门控 | frontend test |
| G-107 | P1 | 无 AD 指标/审计 | `ad_observability.py` + 回滚脚本 | `scripts/plan076-rollback-drill.sh` |

## 波次

### 波次 1（P0，T+7d）

G-001 → G-002 → G-003 → G-004 → G-005 → G-006/G-007 → G-008 → G-009

出口：`bash scripts/verify-plan-076.sh` 工程项 PASS；无语料时仍 BLOCKED。

### 波次 2（P1，T+14d）

G-101–G-107

出口：契约测试 + 前端门控 + 回滚演练文档化。

## 实现偏离说明

| 原计划 | 实际 | 处置 |
| --- | --- | --- |
| `qyunslation/prompts/` 注册表 | `ad_prompt.py` 内嵌模板 | 076b 标注「偏离」；076i 不强制迁移目录 |
| shadow 离线回放 | 曾等同 pilot 开放 | G-002 修正 |
| 20,000「源文词」 | 字符/词混用 | README 统一 `_source_units` |

## 验证

```bash
bash scripts/verify-plan-075.sh
bash scripts/verify-plan-076.sh
bash scripts/plan076-rollback-drill.sh --check-only
```

未挂载 `PLAN076_AD_CORPUS_ROOT` 时总门禁 **BLOCKED** 为预期，不得改写成 PASS。
