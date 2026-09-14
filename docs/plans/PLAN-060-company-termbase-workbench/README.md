# PLAN-060：公司共享专业词库确认工作台

> 状态：**工程实现完成；真实工作台、浏览器尺寸与生产条件待验收**
> 日期：2026-09-14
> 目标分支：`codex/plan-060-company-termbase-workbench`
> Cursor 工作树：`/home/dev/.cursor/worktrees/qyunslation/plan-060-company-termbase-workbench`
> 验收门：`bash scripts/verify-plan-060.sh`

## 目标

将 PLAN-058 的术语库接入实际的 Gradio 翻译工作台：

`译前公司确认词命中 → 翻译 → 译后可定位候选 → 人工确认 → 当前租户公司词库 → 下一文件硬约束复用`

一个租户只有一个内部“公司共享术语库”项目。组织强制词和固定表单词仍优先；公司共享词优先于临床基础、会话和自动候选。精确/别名命中不调用 bge-m3，向量仅可作为未知变体建议，不能自动替换译文。

## 已交付

- `WorkbenchTranslationRun` 绑定 Gradio 临时任务、持久化 Job、文件 hash、语言方向、词库版本、策略与降级状态。
- 仅回环可达且 HMAC 签名的 `/internal/workbench/v1/*` 桥接；浏览器不能提交租户、项目、角色或密钥。
- 普通候选可由员工确认进入本租户公司词库；药品、靶点、剂量、产品、机构、方案编号及冲突缩写只能进入 `pending_admin`，仅管理员可最终裁决。
- PDF 生成每任务受控 glossary CSV；DOCX、PPTX、图片 OCR 及表格/脚注走 sidecar 术语策略；译后失败明示降级，不影响已经成功的翻译任务。
- 专业模式检查器提供候选、上下文、页码/对象定位、单项决定和受限批量精确确认；快速模式提供紧凑的“专业词汇：待确认 N”徽标。
- 参考文献和 preserve 区域不产生术语候选；无法可靠对齐的二进制/OCR 输出不伪装成“零候选”。

## 子计划

| 子计划 | 交付 |
| --- | --- |
| [PLAN-060a](./PLAN-060a-baseline-governance.md) | 运行基线、公司共享项目、角色与审计契约 |
| [PLAN-060b](./PLAN-060b-signed-bridge.md) | 回环 HMAC 桥接、运行记录与部署密钥边界 |
| [PLAN-060c](./PLAN-060c-pretranslation-policy.md) | PDF/Office/PPTX/OCR 的译前术语策略注入 |
| [PLAN-060d](./PLAN-060d-evidence-extraction.md) | 双语证据适配器、风险分级、幂等候选与降级 |
| [PLAN-060e](./PLAN-060e-gradio-review-panel.md) | 快速徽标、专业面板、定位和裁决交互 |
| [PLAN-060f](./PLAN-060f-verification-delivery.md) | 回归、真实工作台验证、WT 与安全部署说明 |

## 验收边界

- 代码与离线测试不等同于真实医药金标。真实 PDF、DOCX 表格/脚注、PPTX、图片 OCR、双栏文献和参考文献保留必须在授权环境补录。
- PostgreSQL、词库桥接密钥、泰州 bge-m3、真实浏览器四尺寸和 Caddy 规则缺失时，LIVE 门必须报告 `BLOCKED`，不得写成 PASS。
- 内部桥接不得由 Caddy 对外反代；管理员角色只能由主机上的 `scripts/manage-term-admin.py` 授予或撤销。
- 本计划不进行全文盲替换，也不训练模型。
