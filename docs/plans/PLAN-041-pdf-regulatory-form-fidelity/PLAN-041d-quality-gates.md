# PLAN-041d：完整性与版式硬门禁

> 状态：**待执行**
> 父计划：[PLAN-041](./PLAN-041-pdf-regulatory-form-fidelity.md)

## 实施

1. 输出逐页、逐表、逐单元格 QC：翻译状态、源/目标语种、保护 token、字号、粗体、溢出及回写结果。
2. 对 `TRANSLATE` 单元格检查中文残留，对 `PRESERVE` 单元格检查不可变 token 一致。
3. `FONT_BELOW_TARGET`、`ROLE_SIZE_DRIFT`、`OVERFLOW`、`MISSING_TARGET` 和 `SOURCE_RESIDUE` 均列为终态阻断错误。
4. 无法在原格安全容纳时走显式 continuation 或失败，不允许缩到微字后静默成功。
5. verifier 缺少必需实样时以非零状态输出 `BLOCKED`。

## 验收

- 普通正文不低于 `max(7pt, 70% 源字号)`，脚注不低于 5.5pt。
- 同角色同层级字号差不超过 0.75pt。
- 任一硬错误都使 Manifest 非 terminal-success，且总门禁失败。
