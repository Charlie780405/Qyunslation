# PLAN-058a：基线、术语分类、指标与 API 契约

> 父计划：[PLAN-058](./README.md)

## 交付

- 明确组织、表单、项目、临床、会话和自动采集六层作用域及固定优先级。
- 定义 Concept、ConceptTerm、候选、出现位置、决定和术语策略包的字段边界。
- 固化 `/terms/resolve`、`/terms/search`、job terms、decide、promote 和 summary 接口。
- 统一 `en/English`、`zh/Simplified Chinese` 等语言方向规范化。

## 完成定义

- 请求必须经过租户和项目边界校验。
- 策略包包含 concept、源词、首选译法、匹配类型、作用域、置信度、位置和 termbase 版本。
- 缓存键包含租户、项目、语言方向、源文件哈希和词库版本。
