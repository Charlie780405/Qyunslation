---
name: PLAN-005 多格式翻译
overview: 在不回退文字 PDF 的 BabelDOC 质量口径下，补齐可编辑 Word、扫描/纯图 PDF（HPD OCR）以及图片嵌字。双栈分流：PDF 仍走 :7860；Word/独立图片走复活的 Qyunslation sidecar。
todos: []
isProject: false
---

# PLAN-005：Word / 扫描 PDF / 图片嵌字

## 目标与不变量

现网 [`translate.qyunsgen.com`](https://translate.qyunsgen.com) 只收 PDF（BabelDOC）。用户要：**可编辑 .docx**、**图片型 PDF 能译出可选中文本**、**图内嵌字覆盖**。

质量/速度继承 PLAN-003/004（004a/c 已因空译文回滚，禁止再封 `num_predict=512`）：

| 不变量 | 口径 |
| --- | --- |
| 模型 | 仅 `qwen3.6:35b-a3b` @ 泰州 `:11434`，**禁止**再走 27b |
| 采样 | `temperature=0`，系统提示含 `/no_think` |
| 术语 | `no_auto_extract_glossary=true`；QX027 用静态 [`/home/dev/pdf2zh/glossaries/qx027n.csv`](/home/dev/pdf2zh/glossaries/qx027n.csv) |
| 文字 PDF | 继续 BabelDOC；JSON fallback 保留；批阈值默认 **200/5**；`num_predict=2000` |
| GPU1 | 只用现成 HPD `:8120`，不扩第二套 OCR、不上 MinerU 重排版 |
| 入口 | **不把 Word 塞进 BabelDOC**（排版链对 docx 无效，且会重蹈 CBP-201 空译文风险） |

## 架构（双栈，按格式分流）

```mermaid
flowchart LR
  user[用户]
  homepage[homepage卡片]
  pdf2