# PLAN-006：审核整治（包名 / 启动 / 安全 / 缺陷）

## 目标

全面整治 qyunslation：彻底完成 `docutranslate`→`qyunslation` 重命名以恢复可重启；砍掉 docling 无条件 import 的启动开销；按实测拐点校准并发；修复安全漏洞与并发/资源缺陷。

## 子计划

| 编号 | 名称 | 依赖 |
| --- | --- | --- |
| 006a | 彻底重命名 | 阶段 0 symlink 兜底 |
| 006b | 启动加速（延迟 docling） | 006a |
| 006c | 模型与并发校准 | 006a |
| 006d | 安全加固 | 006a |
| 006e | 并发缺陷与资源治理 | 006a |
| 006f | CI / 测试 / 卫生 | 006a–006e |

## 质量不变量

- 环境变量前缀保留 `DOCUTRANSLATE_*` 兼容；`QYUNSLATION_*` 优先双读
- 模型继续用泰州 `qwen3.6:35b-a3b`；`THINKING=disable`
- API 鉴权默认关闭（设 `QYUNSLATION_API_TOKEN` 才启用）
- 不改业务翻译 prompt / 工作流语义

## Out of Scope

- 换 DeepSeek 为主力模型
- 重写前端 UI
- 同步上游 DocuTranslate 增量

## 验收

`bash scripts/verify-plan-006.sh` 全绿；无 symlink 下 `import qyunslation.app` 成功；启动显著短于改前。
