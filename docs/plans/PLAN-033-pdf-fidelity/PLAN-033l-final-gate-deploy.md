# PLAN-033l：最终产物总门、部署与回滚

> 状态：**总门已落地；真实最终 PDF 验收 FAIL，未部署**
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 验收门：`bash scripts/verify-plan-033l.sh` 与重写后的 `bash scripts/verify-plan-033.sh`
> 前置：033g–033k

## 目标

总门检查最终 mono/dual PDF，而不是只串单元测试。外部样本缺失必须 `BLOCKED`。生产部署前做 BabelDOC 版本和补丁签名自检；先暂存环境验收，再备份、部署和重启。写清回滚命令和生产烟测。

## 实现边界

改：

- `scripts/verify-plan-033.sh`：检查最终 mono/dual PDF 断言
- 新建 `scripts/verify-plan-033g.sh` … `033l.sh`（若前序子计划已建则只补 033l）
- 部署脚本：BabelDOC 版本 + 补丁签名不匹配则停止部署
- `docs/walkthroughs/WT-033-fidelity-remediation.md`

不改：业务翻译算法本身（本子计划只做门禁与发布）。

## 真实样本断言

`QYUNSLATION_PLAN033_SAMPLE` 必须在场，否则 `BLOCKED`：

- Figure=2，Table=4
- Table 1–4 表题/可译单元格/脚注均有终态执行证据
- Table 1 旋转整页表已翻译
- Table 2–4 无漏译，脚注已译，角色字号与粗体一致
- Figure 1 零截断/越框/漏译；低于目标字号时有告警和高分辨率输出
- 粗体标题仍粗体，普通正文 Regular
- 参考文献整区与原稿一致，LLM 请求数 = 0
- 双语左侧逐页渲染 hash = 原稿；续页重复左侧同样一致
- 最终 PDF 无 PENDING / 漏译 / 截断 / 溢出 / 图形损坏
- `model_trace` 命中 `http://100.67.66.123:11434/v1` + `qwen3.6:35b-a3b`

## 部署顺序

1. 暂存环境跑 033g–033l + 028/029/030e
2. 备份当前 `gui.py` / BabelDOC 补丁 / 服务单元
3. 补丁签名自检
4. 部署并重启服务
5. 生产烟测：health + 小夹具 + 样本关键断言
6. 失败则执行回滚命令并停止宣称完成

## 验收

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | 样本缺失 → `BLOCKED` 非零退出 | 通过 |
| V2 | 样本在场时最终 PDF 断言全过 | 通过或 BLOCKED |
| V3 | 补丁签名不匹配停止部署 | 通过 |
| V4 | WT 记录分支、SHA、门禁、模型、产物、回滚 | 通过 |
| V5 | `verify-plan-033.sh` 与 `verify-plan-033l.sh` | `PASS` 或诚实 `BLOCKED` |
