# PLAN-033：学术 PDF 图表识别与原文不可变

> 状态：**已关闭并部署**（033n @ HEAD `76c75cf`，`verify-plan-033.sh` PASS）
> 日期：2026-09-09
> 基线：`775d0c1`（PLAN-030h）
> 033a–033f 合入：`f83c5ff`（已部署生产）
> 补救分支：`codex/plan-033g-fidelity-remediation`
> 原作者：Codex（2026-09-09 递交）
> 修订：对照仓库实现后收口范围；真实产物验收失败后追加 033g–033l
> 验收门：各子计划独立 `scripts/verify-plan-033a.sh` … `033l.sh`；总门 `scripts/verify-plan-033.sh` 必须检查最终 mono/dual PDF
> 提示词：[PROMPT-PLAN-033-REVISION.md](./PROMPT-PLAN-033-REVISION.md)

## 一句话

033a–033f 修好了题注计数和原文半边不可变，但真实 11 页学术 PDF 的最终产物仍失败。补救必须证明：参考文献整区保留、正文字重正确、四张表真实翻译排版、图片零截断，以及任务实际命中泰州 `qwen3.6:35b-a3b`。

## 历史：033a–033f 已完成并部署

对照 `captions.py`、`manifest_store.py`、`doc_image_prescan.py`、PLAN-030h D1–D5 之后，原稿把六件事捆成一个计划。033a–033f 只关闭了当时可证明的两条用户可感知缺陷：

1. **计数**：同一语义对象不因 span 无空格而失踪。11 页样本 Figure=2、Table=4。
2. **原文不可变**：BabelDOC 的输入永远是原始上传 PDF 的字节；双语左侧与原稿逐页一致。

| 子计划 | 状态 | 实际交付 |
| --- | --- | --- |
| [033a](./PLAN-033a-caption-count.md) | 已完成 | 题注空格与计数契约 |
| [033b](./PLAN-033b-table-geometry.md) | 已完成 | 侧放框线表区域几何，无单元格执行 |
| [033c](./PLAN-033c-original-immutable.md) | 已完成 | BabelDOC 只吃原稿 |
| [033d](./PLAN-033d-references.md) | 已完成 | Manifest `planned_action=skip`，BabelDOC 未消费 |
| [033e](./PLAN-033e-preview-dpi.md) | 已完成 | 当前页 300 DPI 预览 |
| [033f](./PLAN-033f-verify-gate.md) | 已完成 | 旧总门只串子门+结构套件，不查最终 PDF |

**计数正确 ≠ 执行完成。** 真实产物仍有：Table 1 未译、Table 2–4 脚注/字号失败、流程图溢出、正文标题掉粗体、参考文献文章标题被译。

## 补救：033g–033l

| 子计划 | 目标 | 依赖 |
| --- | --- | --- |
| [033g](./PLAN-033g-execution-contract.md) | Manifest 1.2.0、扫描器 1.5.0、块级执行证据、模型溯源 | 无 |
| [033h](./PLAN-033h-references-body-style.md) | 参考文献整区 PRESERVE；正文字重/斜体/栏内节奏 | 033g |
| [033i](./PLAN-033i-table-structure.md) | 旋转无关表格局部坐标与稳定单元格块 | 033g |
| [033j](./PLAN-033j-table-translate-continuation.md) | 表格批量翻译、矢量重排、单语/双语续页 | 033i |
| [033k](./PLAN-033k-image-fit-qc.md) | role-aware fitter、等义精简、对象级 QC | 033g |
| [033l](./PLAN-033l-final-gate-deploy.md) | 最终 PDF 总门、部署自检、回滚与 WT | 033g–033k |
| [033m](./PLAN-033m-final-evidence.md) | 诚实总门 + Table 1–4 切格写出 + HEAD 绑定产物 | 033l |
| [033n](./PLAN-033n-head-evidence-rebind.md) | 当前 HEAD 重跑全链路并重绑 `/tmp/plan033m-<HEAD>/` | 033m |

## Out of Scope

- 030h D1–D5（三栏/海报/`content_profile` 硬编码）
- 引入 Camelot / Java
- 把 Elsevier PDF 提交进仓库
- 改 `glossaries/auto-proper-nouns.csv`
- 直接合并或推送 `main`

## 锁定策略（不得再讨论）

- 参考文献：从章节标题起整区原样保留，标题也不译；Appendix 之后恢复翻译。
- 表格：矢量网格 + 可搜索文字；缺文字层时仅对表区 ≥300 DPI OCR；禁止整表栅格化。
- 图片：换行 → 框内安全扩展 → 方向调整 → 等义精简 → 整组缩小；禁止删末行/截断。
- 模型：任务必须记录最终 `model_id` 与去凭据 endpoint；验收证明命中 `http://100.67.66.123:11434/v1` + `qwen3.6:35b-a3b`。

## 真实样本

- 环境变量：`QYUNSLATION_PLAN033_SAMPLE`
- 本机副本（不入库）：`/home/dev/.hermes/attachments/1-s2.0-S2666636725013958-main.pdf`
- 11 页，SHA-256 `c88ea994746e13904ed012943130896426b8812f939ae14917e1c48f59b2f8dc`
- 样本缺失：总门与 033l **BLOCKED**，禁止 skip 冒充通过

## 验证顺序

1. 各子计划聚焦单元测试
2. `verify-plan-033g.sh` … `verify-plan-033l.sh`
3. 完整 structure 测试
4. `verify-plan-033.sh`
5. `verify-plan-028.sh`
6. `verify-plan-029.sh`
7. `verify-plan-030e.sh`

任一 `FAIL`/`BLOCKED` 不得宣称 PLAN-033 完成。不得用“单元测试通过”代替最终 PDF 验收。

## 交付约定

- 原子提交顺序：文档修订 → 033g → 033h → 033i → 033j → 033k → 033l。
- 精确 `git add <路径>`。
- 全部门禁通过后只推送 `codex/plan-033g-fidelity-remediation`。
