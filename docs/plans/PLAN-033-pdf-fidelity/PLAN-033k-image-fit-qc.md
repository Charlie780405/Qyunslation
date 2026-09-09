# PLAN-033k：图片排版和对象级 QC

> 状态：**已接到生产后处理（object_qc + DPI 重绘），真实样本终态待验收**
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 验收门：`bash scripts/verify-plan-033k.sh`
> 前置：033g

## 目标

建立图片/表格可复用的 role-aware fitter。删除 tier majority bold、私有 outlier 字号和 `lines[:max_lines]` 截断。等义精简保留源文—译文映射。对象级 QC 写入 `.imgtr.json` 和结构 Manifest。

## 根因

现有图片排版用多数投票决定整层粗体，outlier 可用私有字号，装不下就切末行。`.imgtr.json` 没有对象级 QC。字号过小或溢出仍可能标成功。

## 实现边界

改：

- role-aware fitter：标题/标签/正文/脚注分组；同角色字号一致；块级粗体继承原文
- 适配顺序：换行 → 框内安全扩展 → 方向调整 → 等义精简 → 整组缩小
- DPI：默认 ≥300；小字号自动 450/600
- 字号目标：标题 ≥ max(源 80%, 7pt)；标签/正文 ≥ max(源 70%, 6pt)；脚注 ≥ max(源 70%, 5pt)
- 低于目标：继续缩小并记 `FONT_BELOW_TARGET`，**不**因此整项失败；仍必须零截断、零溢出
- QC 码：`UNTRANSLATED`、`TRUNCATED`、`OVERFLOW`、`FONT_BELOW_TARGET`、`ROLE_SIZE_DRIFT`、`WEIGHT_MISMATCH`、`GRAPHICS_DAMAGE`

不改：表格单元格提取（033i）、续页策略（033j）、术语表 CSV。

## 失败策略

| 码 | 级别 |
| --- | --- |
| UNTRANSLATED / TRUNCATED / OVERFLOW / GRAPHICS_DAMAGE | 硬失败 |
| WEIGHT_MISMATCH / ROLE_SIZE_DRIFT | 硬失败 |
| FONT_BELOW_TARGET | 警告，不单独让整项失败 |

## 验收

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | 无 `lines[:max_lines]` / majority bold | 通过 |
| V2 | 块级粗体继承，禁止层投票 | 通过 |
| V3 | 等义精简保留映射且不丢数值 | 通过 |
| V4 | 小字号输出 DPI ∈ {450, 600} | 通过 |
| V5 | QC 写入 `.imgtr.json` 与 Manifest | 通过 |
| V6 | `verify-plan-033k.sh` | `SUMMARY: PASS fail=0` |
