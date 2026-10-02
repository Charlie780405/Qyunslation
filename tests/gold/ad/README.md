# PLAN-076 AD 双向评测语料

本目录只接受经过授权的、可追溯的真实医学研究或临床研究文档切片：

- `*.source.en.txt` + `*.target.zh.txt`：英译中；
- `*.source.zh.txt` + `*.target.en.txt`：中译英。

目标门槛是每个方向至少 12 个真实文档、20,000 **源文计量单位**（拉丁词元 + CJK 字符，与 PLAN-076 README 一致）和 100 个 **annotation 挑战片段**（按 `annotations.json` 条目计数，非 case 数）。未完成专家脱敏与双盲标注前，不得用合成文本或同一文档复制填充目录。评测脚本会在数据不足时返回 `BLOCKED`。

内部授权语料不要复制进 Git，挂载到受控目录后通过环境变量指定：

```bash
PLAN076_AD_CORPUS_ROOT=/secure/plan076/ad \
  .venv/bin/python scripts/plan076-ad-eval.py --check-corpus --direction both
```

`manifest.json` 必须符合本目录的 `manifest.schema.json`，每个 `annotations.json` 遵循 `annotations.schema.json`，并为每个锁定 case 提供源文、参考译文、annotation 文件及 SHA-256。评测器只读取 manifest 登记的文件；未登记的临时文件不会进入分母。

语料合同通过后，`--baseline-only` 会使用显式配置的 OpenAI-compatible 内网端点生成通用提示词机器译文；`--run-model candidate` 运行 AD 提示词，`--run-model both` 运行两者。端点、模型和参数摘要写入 `var/plan076-ad-eval/runs/<run_id>/report.json`，译文只落在该不可复用的 run 目录并以 SHA-256 追踪，模型请求失败或确定性 QA blocker 均不会判为 PASS：

为防止受控语料外发，公网端点默认拒绝；只有经过数据治理批准时才显式增加 `--allow-external-endpoint`。

专家双盲结果使用 `expert-review.schema.json`，只提交 case 级盲选、严重度和仲裁结果，不提交模型名、完整 prompt 或原文。导入命令：

```bash
.venv/bin/python scripts/plan076-ad-eval.py \
  --expert-review /secure/plan076/ad/expert-review.json \
  --direction both
```

结果必须同时满足 Critical=0、Major≤1/1,000 源文单位、Cohen κ≥0.70、候选盲选偏好≥70%，否则状态为 `FAIL` 或 `BLOCKED`，产品仍只能显示“AD 内部测试版”。

Pilot soak 使用 `pilot-report.schema.json`，必须覆盖 20 个真实任务，且 `en-zh/医学研究文献`、`en-zh/临床研究文档`、`zh-en/医学研究文献`、`zh-en/临床研究文档` 四个组合各至少 5 个：

```bash
.venv/bin/python scripts/plan076-ad-eval.py \
  --pilot-report /secure/plan076/ad/pilot.json \
  --direction both
```

```bash
PLAN076_AD_CORPUS_ROOT=/secure/plan076/ad \
  .venv/bin/python scripts/plan076-ad-eval.py \
  --baseline-only --base-url http://internal-gateway:11434/v1 \
  --model qwen3.6:35b-a3b
```
