# PLAN-073c：资料等级驱动模型与 DeepSeek

## 策略

| 等级 | 全文翻译 | 术语建议 |
| --- | --- | --- |
| confidential | 本地 Qwen | 无外部 |
| internal | 本地 Qwen | DeepSeek 脱敏片段（可选） |
| public | DeepSeek 或 Qwen | DeepSeek 脱敏片段（可选） |

## 交付

- `_prepare_runtime_config` 按 `model_snapshot` 生成每任务 runner-config.toml。
- 前端资料等级联动 `GET /model-profiles`，创建任务传 `model_profile_id`。
- `QYUNSLATION_DEEPSEEK_API_KEY` 未配置时 DeepSeek 置灰；verify BLOCKED。

## 验收

- 机密任务 config 无外部端点；公开+DeepSeek 时 `deepseek=true`。
