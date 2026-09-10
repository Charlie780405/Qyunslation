# PLAN-030id：补丁供应链与发布收口

> 状态：**已完成**（隶属 [PLAN-030i](./PLAN-030i-delivery-closure.md)）
> 映射：父纲领 Checkpoint D §「生产补丁可幂等、可回滚」「用户批准视觉金样后才允许部署」

## 目标

将分散的 `apply-pdf2zh-*.py` 与 systemd `ExecStartPre` 链文档化、可验证；部署前 BabelDOC 签名门纳入 030i 总门；视觉金样有人工批准记录。

## 交付项

1. **补丁清单**：`docs/contracts/pdf2zh-patch-order.md` 列出全部补丁脚本、依赖顺序、marker 名、负责 PLAN；与 `scripts/pdf2zh.service` 一致。
2. **签名门泛化**：扩展 `check-babeldoc-fidelity-033l.py` 或新建 `check-babeldoc-patch-signature.py`，由 `verify-plan-030i.sh` 调用；失败 exit 2。
3. **幂等回归**：`verify-plan-021.sh` 中「双次 apply 不重复插入」模式纳入 030i 抽检（至少 docimg/docprofile/prescan）。
4. **视觉金样清单**：`docs/contracts/visual-gold-030.md` 列样本路径、hash、批准人/日期；未批准项在 WT 标 INFO，不阻塞 merge。
5. **WT-030i**：记录一次完整「verify → deploy-pdf2zh-cutover → 烟囱」证据；回滚步骤可执行。

## 关键文件

- `scripts/pdf2zh.service`
- `scripts/check-babeldoc-fidelity-033l.py`
- `scripts/verify-plan-030i.sh`
- `docs/contracts/pdf2zh-patch-order.md`（新建）
- `docs/contracts/visual-gold-030.md`（新建）
- `docs/walkthroughs/WT-030i-delivery-closure.md`（收口时写）

## 验证

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | 补丁顺序 doc 与 service grep 一致 | 人工或 lint 脚本 |
| V2 | check-babeldoc 在 prod venv | exit 0 |
| V3 | 双次 apply 关键补丁 | marker 计数不增长 |
| V4 | visual-gold 清单每项有 hash | 缺批准日期则 verify 警告非 FAIL |

## Out of Scope

- 033 新补丁开发
- 全自动像素 diff CI
- 跨机 Hermes 绝对路径消除（可记债，不属 030i 必达）
