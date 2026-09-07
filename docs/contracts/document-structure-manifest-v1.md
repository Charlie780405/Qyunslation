# DocumentStructureManifest v1 合同

本合同定义 PLAN-030 各格式扫描器、翻译执行器、UI 与验收之间的稳定公共边界。设计理由见 [ADR-001](../decisions/ADR-001-format-profile-manifest.md)。JSON Schema 由 Python 模型生成，二者漂移会使验证失败。

## 术语

| 术语 | 定义 |
| --- | --- |
| semantic object | 用户可理解且可独立规划/审计的对象，如 Figure、Table、文本框或 Poster 分区 |
| physical resource | PDF xref/drawing、OOXML part/relationship、shape、像素块等底层资源 |
| occurrence | 同一底层资源在特定画布位置的一次显示；共享资源可以有多个 occurrence |
| canvas | 带尺寸、坐标空间和阅读规则的页面、节、幻灯片或 Poster 画布 |
| content profile | 与文件格式无关的内容结构先验 |
| processing mode | `NATIVE`、`RENDERED` 或 `HYBRID` 执行方式 |
| evidence | 探测器对对象分类、边界或关联的可追踪证据，不直接构成用户计数 |

Figure/Table 主计数来自去重后的语义对象，不来自 bitmap、xref、drawing、shape 或 detector box 数量。

## 版本

- 当前版本为 `1.0.0`。
- 相同 major 可增加可选字段；不得删除字段或改变已有字段语义。
- 读取器接受相同 major 的未知扩展字段；写入器只产生当前模型字段。
- 未知 major 返回 `MANIFEST_VERSION_UNSUPPORTED`。
- 规范化 JSON 使用排序键和 UTF-8；`manifest_id` 从不包含 `created_at` 的稳定载荷生成。

## 身份

- `document.source_sha256` 是完整源文件 SHA-256，格式为 64 个小写十六进制字符。
- `document.fast_fingerprint` 可选，只用于快速缓存，不得参与安全或最终身份判断。
- `canvas_id` 在文档内唯一，例如 `page:1`、`slide:2`、`poster:1`。
- `object_id` 在文档内唯一且确定性生成；不得仅使用 detector 返回顺序。
- `semantic_id` 可选且供人阅读，例如 `figure:5`；`semantic_scope` 区分正文、补充材料等编号域。

## 坐标

canonical 坐标以左上角为原点。每个 canvas 显式提供：

- `width`、`height`：严格大于 0。
- `unit`：`PT` 或 `PX`。
- `rotation`：`0 / 90 / 180 / 270`。
- `layout_mode`：`SINGLE / DOUBLE / MULTI / MIXED / FREEFORM`。

对象 bbox 必须满足 `0 <= x0 < x1 <= width`、`0 <= y0 < y1 <= height`。PDF、OOXML 和图片原始坐标及变换信息进入 `source_geometry`，不得覆盖 canonical bbox。

## 格式、画像和模式

三个字段彼此正交：

- `source_format`：实际输入格式。
- `content_profile`：`RESEARCH_ARTICLE / REVIEW_ARTICLE / PRESENTATION / POSTER / REGULATORY / LETTER / GENERIC`。
- `selected_mode`：`NATIVE / RENDERED / HYBRID`。

`profile_source=AUTO` 时必须包含置信度和证据；`USER_OVERRIDE` 时保留自动建议供审计。格式能力产品等级和 runtime state 分开返回。

## 对象

所有对象共享：`type`、`object_id`、`canvas_id`、`bbox`、`representation`、`source_refs`、`execution_status`。`type` 是判别字段，类型专属数据放在对应对象模型中。

首批对象类型：`BODY / CAPTION / FIGURE / TABLE / TEXT_BOX / SHAPE / IMAGE / POSTER_SECTION`。

Figure/Table 可以带 `semantic_id`、题注关联和子对象。IMAGE 代表未被语义归并的独立图片 occurrence，不能自动计为 Figure。

## 状态和问题

执行状态：

- `PENDING`
- `TRANSLATING`
- `TRANSLATED`
- `EXPLICITLY_SKIPPED`
- `FAILED_SOFT`
- `FAILED_HARD`

跳过和失败状态必须包含稳定 reason code。`FAILED_SOFT` 保留原对象；`FAILED_HARD` 阻止成功交付。

问题结构固定为：`code`、`severity`、`stage`、可选 `object_id`、`retryable`、`message` 和 `details`。程序只依赖 `code`，`message` 可以本地化。

## 摘要

`summary` 是 `objects[]` 与 issues 的派生视图。模型必须拒绝调用方提供的矛盾摘要；UI 不得直接相加 physical resource 数形成 Figure/Table 主计数。

## 扩展

非稳定、供应商或探测器专属数据放在 `extensions`，键必须是有命名空间的字符串，例如 `qyunslation.doclayout.v1`。核心消费者忽略不认识的扩展，但必须保留同 major 中不理解的数据以支持往返。
