# PLAN-076 AD 双向评测语料

本目录只接受经过授权的、可追溯的真实医学研究或临床研究文档切片：

- `*.source.en.txt` + `*.target.zh.txt`：英译中；
- `*.source.zh.txt` + `*.target.en.txt`：中译英。

目标门槛是每个方向至少 12 个真实文档、20,000 个源文字符和 100 个风险挑战片段。未完成专家脱敏与双盲标注前，不得用合成文本或同一文档复制填充目录。评测脚本会在数据不足时返回 `BLOCKED`。

内部授权语料不要复制进 Git，挂载到受控目录后通过环境变量指定：

```bash
PLAN076_AD_CORPUS_ROOT=/secure/plan076/ad \
  .venv/bin/python scripts/plan076-ad-eval.py --check-corpus --direction both
```

`manifest.json` 必须符合本目录的 `manifest.schema.json`，并为每个锁定 case 提供源文、参考译文、annotation 文件及 SHA-256。评测器只读取 manifest 登记的文件；未登记的临时文件不会进入分母。`--baseline-only` 在接入真实模型运行器前会保持 `BLOCKED`，避免把参考译文检查误报成通用提示词基线。
