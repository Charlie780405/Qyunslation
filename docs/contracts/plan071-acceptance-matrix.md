# PLAN-071 验收矩阵

> 父计划：[PLAN-071](../plans/PLAN-071-translation-quality-pipeline/README.md)
> **禁止**：仅以命令退出码 0 / runner `status=succeeded` 判定翻译成功。

图例：R=必过，G=灰度后必过，—=不适用，B=缺真实浏览器证据则整包 BLOCKED。

## 1. 格式 × 质量门

| 场景 | Manifest 反查 | 阶段事件真实 | PRESERVE/版式 | QA blocker | 人工审核 | 正式下载门禁 |
| --- | --- | --- | --- | --- | --- | --- |
| PDF 文本 | R | R | —/R 段落 | R | R | R |
| PDF 扫描 FDA | R | R（含 OCR） | R Logo/签名/原子 span | R | R | R |
| PDF 表格密集 | R | R table_figure | R 行列合并数字 | R | R | R |
| PDF 图片密集 | R | R table_figure | R 底图不重绘 | R | R | R |
| DOCX | R | R | R OOXML/媒体 | R | R | R |
| PPTX | R | R | R 母版/shape | R | R | R |
| PNG/JPEG | R | R | R 遮罩叠字 | R | R | R |

## 2. 状态机与进度

| 检查项 | 要求 | 证据 |
| --- | --- | --- |
| CLI/执行器完成 | 不得直接 succeeded；进入 layout 或 qa | 事件表 + API |
| skipped | 不适用阶段写 skipped，UI 不显示为 completed | events + StageTimeline |
| progress=null | 无分母时不确定进度 | events.progress |
| generation 隔离 | 错代际事件/预览不覆盖 | API 测试 |
| 重启 reconcile | 已完成阶段不重复执行 | pipeline 测试 |

## 3. 权限与模型

| 检查项 | 要求 |
| --- | --- |
| confidential | 仅 internal-qwen-quality；禁外部 |
| internal 全文 | 仅 Qwen；术语可脱敏后 DeepSeek |
| internal API 作弊 | 指定 public-deepseek-flash 全文 → 拒绝 |
| public | Qwen 或 DeepSeek Flash |
| 密钥 | UI 仅已配置/未配置；日志无 Key |
| admin policies | 路由+API 双门禁 can_manage_policy |

## 4. 设置与前端

| 检查项 | 要求 | 浏览器 |
| --- | --- | --- |
| 设置 section URL | 刷新/前进后退恢复 | B |
| 阅读与交互 | 字体/动效/密度立即生效 | B |
| 阶段条 | 只读 events，无硬编码理想完成态 | B |
| 任务详情 | `/workbench/:runId` 独立页；预览恢复 | B |
| a11y | axe/键盘/200% 字体/减动效 | B |

## 5. 安全

| 检查项 | 要求 |
| --- | --- |
| 脱敏失败 | 回退内网，不外发 |
| CSRF / 跨租户 | 预览与下载拒绝 |
| 危险文件名 | 存储与 Content-Disposition 安全 |
| 正式下载绕过 | 无 approved 无法拿到 formal |

## 6. 发布总闸

| 项 | 状态机 |
| --- | --- |
| 单测/集成/契约 | 全绿 |
| Alembic up/down | 全绿 |
| 七类真实样本 | G；FDA 为 R |
| Qwen/DeepSeek 盲测 | DeepSeek 未达标只标试验 |
| Chrome DevTools 闭环 | 缺则 **BLOCKED** |
| 日志↔事件↔QA↔审核↔产物可追溯 | R |

## 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-10-01 | 071a 初版 |
