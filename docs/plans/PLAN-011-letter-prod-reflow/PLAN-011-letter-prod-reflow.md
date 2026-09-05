# PLAN-011：正式书信重绘接入生产 GUI

把 PLAN-010 已验收的「OCR 全文 → a3b → 空白页 `kv_reinsert`」接到 `translate.qyunsgen.com`。不改泰州 HPD。不改 PLAN-010 正文。

## 目标

扫描件 + 文档类型「正式书信」（或自动识别为 letter）时，GUI **不再把 BabelDOC PDF 当终稿**；下载的 mono/dual 都是重绘页。

## 实现

| 项 | 做法 |
| --- | --- |
| `letter_pipeline.py` | 整本填 `text_zh`（跨页上下文）→ 空白页 `reflow` → logo 回插 |
| `hpd_ocr.py` | letter profile **必写** `*.hpd-debug.json` |
| `apply-pdf2zh-docprofile.py` | 修 HPD 后错误缩进；HPD 后若有 debug 则 `_qy_letter_reflow` 并 return |
| `pdf2zh.service` | 已有 `apply-pdf2zh-docprofile.py` ExecStartPre |

## 不做

- 不改泰州 HPD `/parse`
- 文献 / IND 仍走 BabelDOC
- 无 HPD debug 的原生文字书信仍走 BabelDOC

## 验收

```bash
python3 -m unittest scripts.test_letter_pipeline scripts.test_kv_reinsert
python3 scripts/apply-pdf2zh-docprofile.py
python3 -c "import ast; ast.parse(open('/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py').read())"
bash scripts/verify-plan-011.sh
```

部署：`systemctl --user restart pdf2zh.service`；`:7860` 200。
