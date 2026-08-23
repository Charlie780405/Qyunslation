# PLAN-003b：泰州 Ollama 调度（GPU0）

## 目标

用 **现网 35b-a3b** 翻译段长度重测并发曲线，设置 `KEEP_ALIVE` / `NUM_PARALLEL`，有据再调 Vultr `qps`。

## Task B1 — 基准脚本

`scripts/benchmark-ollama-003b.py`：

- 目标：`http://100.67.66.123:11434`
- 模型：`qwen3.6:35b-a3b`
- Prompt：仿 BabelDOC 段落（200–400 英文字），`/no_think` 系统提示
- 并发：1 / 2 / 4，记录 wall_s、ok、均摊 latency
- 输出：`docs/perf/baseline-003b.json`

## Task B2 — 泰州 systemd 环境

`scripts/deploy-taizhou-ollama-003b.sh`（SSH `genscend@100.67.66.123`）：

```ini
Environment=OLLAMA_KEEP_ALIVE=-1
Environment=OLLAMA_NUM_PARALLEL=<曲线最优>
```

仅改 GPU0 Ollama 服务；不动 HPD（GPU1）。

## Task B3 — Vultr qps

仅当 B2 证明 4 并行均摊明显优于 2 且 VRAM 安全时：

```toml
qps = 4
pool_max_workers = 4
```

否则保持 `qps = 2`。

## 验收

| # | 项 | 期望 |
| --- | --- | --- |
| B-V1 | `baseline-003b.json` | 含 1/2/4 曲线 |
| B-V2 | HPD | `:8120/health` = ok |
| B-V3 | 烟测 | 同等页数墙钟优于 PLAN-003 基线 40%+（关术语前提下） |

## 回滚

去掉泰州 `OLLAMA_*` 环境变量，重启 ollama；Vultr `qps` 改回 2。
