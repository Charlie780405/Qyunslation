# PLAN-034f：模型网关与医药 QA

> 状态：**已编码**（网关 + provenance + 风险分级 + 确定性 QA + 可选一轮 repair）
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：[034d](./PLAN-034d-concept-termbase.md)、[034e](./PLAN-034e-translation-memory.md)
> 验收门：`bash scripts/verify-plan-034f.sh`
> Walkthrough：[WT-034f](../../walkthroughs/WT-034f-model-gateway-qa.md)

## 目标

统一**模型网关**解耦 PDF（pdf2zh `config.toml`）与 Office（`.env` `DOCUTRANSLATE_*`）双配置；风险分级；翻译—复核—修复；确定性校验覆盖医药关键项。基线仍为 `qwen3.6:35b-a3b`，不训练新模型。

## 交付（已落地）

1. `TranslatorProvider`：`QwenOllamaProvider`（`translate` / `review` / `repair`）；`fast`/`fallback` 槽位存在但未接线 → `ProfileNotWiredError`。
2. 任务 provenance：写入 `job.provenance`（`model_id`、去凭据 endpoint、提示词/术语/TM/算法/渲染器版本、profile、provider）；**不记录 API Key**。
3. 风险分级：`grade_risk(domain, role)`；参考文献 `PRESERVE`；表/剂量 `critical`。
4. 流水线：`translate → QA → (可选 review) → (可选一轮 repair) → 再检`；`POST /api/v1/qa/run`。
5. 确定性 12 项：数字、剂量、单位、百分比、日期、否定、缩写、术语、引用、表格关系、遗漏、参考文献。
6. PDF：`scripts/plan034f-sync-pdf2zh-model.py` 投影 model id；**不**改 BabelDOC 进程内循环。

## 判据

- 一处 `profiles.yaml` + `QYUNSLATION_GATEWAY_PROFILE` 影响 Office；PDF 经同步脚本双写说明。
- 金标任务 provenance 完整且无密钥。
- Critical 确定性失败 → `blocked`；可写 job `status=qa_blocked`。

## Out of Scope

- OPUS-MT / CTranslate2 / COMET
- NLLB / LibreTranslate / Argos
- 向量检索、TM/BabelDOC 自动套用、034g 审校 UI

## 完成定义

- [x] 网关 + provenance 写入 job
- [x] 确定性检查清单全部有自动化或明确豁免理由
- [x] WT-034f 记录泰州 Ollama 基线命中证明（verify：不可达 → BLOCKED）
