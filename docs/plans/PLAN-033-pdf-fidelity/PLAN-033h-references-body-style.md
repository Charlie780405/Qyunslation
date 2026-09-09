# PLAN-033h：参考文献硬保留和正文样式

> 状态：**已实现，门禁待总验收**
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 验收门：`bash scripts/verify-plan-033h.sh`
> 前置：033g

## 目标

参考文献从章节标题起整区 `PRESERVE`，零 LLM 请求。原文粗体/斜粗体标题在译文中保持字重和斜体；普通正文不得误加粗；栏宽、阅读顺序和正文基线节奏保持，段落间不得出现异常巨大空白。

## 根因

033d 只在扫描结果写 `planned_action=skip`。BabelDOC 在把段落送给 LLM 之前不消费 Manifest。标题仍走 `babeldoc_text_layer`，条目也可能因跨栏/续页重新入队。字重只看 PDF flags，认不出字体名里的 Bold/Semibold/Black/`.B`。

## 实现边界

改：

- `qyunslation/structure/references.py`：标题也 `PRESERVE`；Appendix/Supplement 结束参考文献区
- `qyunslation/structure/scan_pdf.py`：heading/entry 均 `planned_action=preserve`，`translation_policy=PRESERVE`
- BabelDOC 补丁：送 LLM 前消费 Manifest；参考文献不进请求、术语抽取、共享/标题上下文
- 字重推断：flags ∪ 字体名模式
- 栏内行距/段距：跟源文基线节奏，禁止把普通段距撑成异常空白

不改：表格执行（033i/j）、图片 fitter（033k）、术语表 CSV。

## 失败策略

| 情况 | 动作 |
| --- | --- |
| 参考文献块仍进入 LLM | 硬失败（LLM spy 计数 > 0） |
| 标题被翻译 | 硬失败 |
| Appendix 后正文被 PRESERVE | 硬失败 |
| 粗体标题译成 Regular | 硬失败 |
| 普通正文被加粗 | 硬失败 |

## 验收

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | 标题+条目 `translation_policy=PRESERVE` | 通过 |
| V2 | LLM spy：参考文献请求数 = 0 | 通过 |
| V3 | 正文 `see [12]` 仍翻译 | 通过 |
| V4 | harvest 不含参考文献标题与条目 | 通过 |
| V5 | 字体名 Bold/Semibold/Black/`.B` 判为粗体 | 通过 |
| V6 | 合成件栏内段距无异常巨大空白 | 通过 |
| V7 | `verify-plan-033h.sh` | `SUMMARY: PASS fail=0` |
