# WT-033 学术 PDF 最终产物保真补救（033g–033l）

> 计划：[PLAN-033](../plans/PLAN-033-pdf-fidelity/PLAN-033-pdf-fidelity.md)
> 分支：`codex/plan-033g-fidelity-remediation`
> 日期：2026-09-09
> 结论：**未完成。** 子计划代码与聚焦门禁已入库，但真实 11 页最终 PDF 仍是补救前产物，`verify-plan-033l.sh` 报 `REFERENCES_HEADING_TRANSLATED`。不得宣称 PLAN-033 修订完成。

## 分支与提交

| 提交 | SHA |
| --- | --- |
| 提示词与 033g–033l 计划 | `29274bd` |
| 033g 执行契约与模型溯源 | `a677aeb` |
| 033h 参考文献与正文字重 | `046d321` |
| 033i 表格结构化 | `97d197f` |
| 033j 表格翻译与续页 | `ddcfcad` |
| 033k 图片排版与 QC | `9b1c805` |
| 033l 总门与本 WT | 本提交 |

工作区：`/home/dev/.codex/worktrees/033g/qyunslation`  
保护：未改动、未提交 `glossaries/auto-proper-nouns.csv`。

## 模型与端点

- 锁定：`qwen3.6:35b-a3b` @ `http://100.67.66.123:11434/v1`
- 代码：`bind_task_model_trace` 写入去凭据 `extensions.model_trace`
- **真实样本验收未重跑翻译**，因此没有新任务的实际命中日志。不得用 `.env` 默认值代替。

## 门禁

| 门禁 | 结果 |
| --- | --- |
| verify-plan-033g.sh | PASS |
| verify-plan-033h.sh | PASS |
| verify-plan-033i.sh | PASS |
| verify-plan-033j.sh | PASS |
| verify-plan-033k.sh | PASS |
| verify-plan-033l.sh | **FAIL** `REFERENCES_HEADING_TRANSLATED` |
| verify-plan-033.sh | **FAIL**（033l 失败） |
| verify-plan-028.sh | 未因 033l 失败而宣称通过；本 WT 提交后另跑 |
| verify-plan-029.sh | 同上 |
| verify-plan-030e.sh | 同上 |

样本 `QYUNSLATION_PLAN033_SAMPLE` 本机在场：`/home/dev/.hermes/attachments/1-s2.0-S2666636725013958-main.pdf`（hash 吻合）。扫描计数 Figure=2 / Table=4。

## 真实产物

现用输出仍是补救前会话，不是本分支重译：

- mono：`/home/dev/pdf2zh/pdf2zh_files/a0de9853-5da9-4db3-a989-b74b0ab87d40/1-s2.0-S2666636725013958-main.no_watermark.zh-CN.mono.pdf`
- dual：`.../1-s2.0-S2666636725013958-main.no_watermark.zh-CN.dual.pdf`
- 旧 dual 末页出现「参考文献」而看不到原标题 `References` → 033l 硬失败

未证明：Table 1–4 终态执行证据、Table 1 旋转表已译、Figure 1 零截断、粗体标题、参考文献 LLM 请求数为 0、双语左侧 hash、续页左侧原稿一致。

## 部署 / 烟测 / 回滚

**未部署生产。** BabelDOC 现场补丁签名自检 `scripts/check-babeldoc-fidelity-033l.py` 在未 apply 033h 前应停止部署。

暂存验收顺序（通过后才允许）：

1. `python3 scripts/apply-pdf2zh-fidelity-033h.py`
2. `python3 scripts/check-babeldoc-fidelity-033l.py`
3. 用泰州端点重译 11 页样本，设置 `QYUNSLATION_PLAN033_MONO` / `DUAL`
4. `bash scripts/verify-plan-033l.sh` 与 `verify-plan-033.sh` 必须 PASS
5. 再备份、`systemctl --user restart pdf2zh.service`、烟测 `:7860`

回滚：

```bash
cp /home/dev/pdf2zh/gui.py.bak-plan033c-20260908T234059Z /home/dev/pdf2zh/gui.py
# 从 pdf2zh.service 去掉 apply-pdf2zh-fidelity-033h.py 后
systemctl --user daemon-reload
systemctl --user restart pdf2zh.service
```

## 尚未完成

1. 对现场 BabelDOC 应用 033h 补丁并重译 11 页样本。
2. 用新 mono/dual 通过 033l 全部最终 PDF 断言。
3. 生产部署、烟测、回滚演练。
4. 推送 `codex/plan-033g-fidelity-remediation`（须全部门禁 PASS 后）。
