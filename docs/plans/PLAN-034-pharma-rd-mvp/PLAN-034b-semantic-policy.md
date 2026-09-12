# PLAN-034b：医药文档语义策略（Manifest 1.3.0）

> 状态：**待编码**（骨架文档）
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：[034a](./PLAN-034a-gold-benchmark.md)

## 目标

Manifest **1.3.0** 向后兼容扩展：翻译策略、样式与来源不可变契约、领域与风险级别、知识资产版本溯源。收口代码 `1.2.0` 与合同文档写 `1.0.0` 的 drift。

## 增量契约

在现有 `DocumentStructureManifest`（`qyunslation/structure/models.py`）上增加或补全：

| 领域 | 内容 |
| --- | --- |
| `translation_policy` | 现有 `TRANSLATE` / `PRESERVE` / `PROTECT_TOKENS`；**新增** `TERM_ONLY`、`HUMAN_REVIEW` |
| 样式 | 字体、字号、粗体、斜体、**颜色、旋转、对齐、行距**（033h 已有字重/斜体基座） |
| 版面 | 页面、栏、阅读顺序、边界框、对象关系 |
| 资产 | 原始资源哈希、派生资源引用（延续 033c 不可变） |
| 元数据 | 文档领域、风险级别 |
| 溯源 | 模型、提示词、术语库、TM、算法、渲染器版本（延续 033g） |

## 锁定规则

- 参考文献整区标记 `PRESERVE`，**不得**进入 LLM、术语抽取或上下文（033d/h 已落地执行侧；1.3.0 写入契约字段）。
- 相同 major 可增可选字段；不得删除或改变已有字段语义。
- 更新 `docs/contracts/document-structure-manifest-v1.md` 版本号与字段表，与 Python 模型一致。

## 判据

- schema_version = `1.3.0`；旧 1.2.0 清单仍可读。
- 金标文献参考文献区 policy = PRESERVE；扫描器与 BabelDOC 策略一致。
- 合同文档与 `models.py` 无版本 drift。

## Out of Scope

- 换 Docling/Paddle 做结构识别
- 实现审校队列（→ 034g，仅预留 `HUMAN_REVIEW` 枚举）

## 完成定义

- [ ] 模型 + 合同 + 迁移说明
- [ ] 扫描器写入新字段的最小路径
- [ ] verify 断言 1.3.0 与 PRESERVE 参考文献
