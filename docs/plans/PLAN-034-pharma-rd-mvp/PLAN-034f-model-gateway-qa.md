# PLAN-034f：模型网关与医药 QA

> 状态：**待编码**（骨架文档）
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：[034d](./PLAN-034d-concept-termbase.md)、[034e](./PLAN-034e-translation-memory.md)

## 目标

统一**模型网关**解耦 PDF（pdf2zh `config.toml`）与 Office（`.env` `DOCUTRANSLATE_*`）双配置；风险分级；翻译—复核—修复；确定性校验覆盖医药关键项。基线仍为 `qwen3.6:35b-a3b`，不训练新模型。

## 现状问题

- PDF 换模型：改 `/home/dev/pdf2zh/config.toml` + 重启 pdf2zh。
- Office 换模型：改 `.env`。
- **无单一切换点** → 「高质量 / 快速 / 备用」多档落不了地。
- 现有 QC **全是结构性**；无语义风险分级与译后修复环。

## 交付

1. `TranslatorProvider` 网关接口：至少 `QwenOllamaProvider`；预留快速/备用槽位（实现可后置）。
2. 任务 provenance：最终解析 `model_id`、去凭据 endpoint、提示词版本、术语库/TM/算法/渲染器版本；**不记录 API Key**（延续 033g）。
3. 风险分级：按文档领域 + 对象角色（正文/表/图注/参考文献）分流策略。
4. 流水线：翻译 → 确定性 QA →（可选）模型复核 → 修复 → 再检。
5. **确定性检查**必须覆盖：数字、剂量、单位、百分比、日期、否定、缩写、术语、引用、表格关系、遗漏、参考文献保护。复用并编排现有 `protect` / `table_qc` / `text_sanitize` / `page_qc`，补齐缺口项。

## 判据

- 一处配置可同时影响 PDF 与 Office 解析到的模型（或明确文档说明双写同步策略）。
- 金标任务 provenance 完整且无密钥。
- Critical 确定性失败阻断发布。

## Out of Scope

- 立即接入 OPUS-MT / CTranslate2 / COMET（可预留接口；本期不强制）
- NLLB / LibreTranslate / Argos 主流程

## 完成定义

- [ ] 网关 + provenance 写入 job
- [ ] 确定性检查清单全部有自动化或明确豁免理由
- [ ] WT-034f 记录泰州 Ollama 基线命中证明
