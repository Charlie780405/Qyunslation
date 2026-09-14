# PLAN-058e：人工裁决、别名和作用域治理

> 父计划：[PLAN-058](./README.md)

## 交付

- 审校摘要展示源词、实际译法、推荐译法、类型、来源、置信度、次数、上下文和所有位置。
- 支持 approve、编辑后 approve、merge、do_not_translate、reject、别名/缩写添加。
- 采用候选 version 乐观锁；普通成员默认只能写当前 project 词库。
- org、form、clinical 等高层作用域必须由 term_admin/admin/owner 提升并记录审计。

## 完成定义

- 批量批准只允许服务端判定为 exact/alias 的低风险候选。
- 新词、多义词、专有名词和冲突词必须逐条确认。
- 术语管理员提升不会跨租户或跨项目读取 Concept。
