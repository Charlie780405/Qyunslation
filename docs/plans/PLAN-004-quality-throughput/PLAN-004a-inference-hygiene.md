# PLAN-004a：推理卫生

## 背景

- 003b 均摊：1/2/4 = 3.11 / 2.65 / **2.42s**
- 泰州 `ollama.service.d/override.conf` 已有 `OLLAMA_NUM_CTX=8192`，但 35b 子进程曾出现 **`-c 262144`**
- `ollama.py`：`num_predict = max(当前, len(text)*5)` 无上限
- `config.toml` `[ollama_detail] num_predict = 2000`

## Task A1 — 核对 llama-server

```bash
ssh genscend@100.67.66.123 'ps aux | grep llama-server | grep -v grep'
```

记录 `-c`、`-np` 写入 `docs/perf/baseline-004a.json` 的 `observed_llama_server`。

## Task A2 — 强制 ctx

`scripts/deploy-taizhou-ollama-004a.sh` 确保：

```ini
Environment=OLLAMA_NUM_CTX=8192
Environment=OLLAMA_NUM_PARALLEL=4
Environment=OLLAMA_KEEP_ALIVE=-1
```

重启后 35b `-c <= 16384` 且 `-np=4`；`curl :8120/health` = ok。

## Task A3 — 封顶 num_predict

1. `/home/dev/pdf2zh/config.toml`：`num_predict = 512`
2. `apply-pdf2zh-throughput.py`：`len(text)*5` 结果 **min(计算值, 1024)**

## Task A4 — 重跑并发曲线

```bash
python3 scripts/benchmark-ollama-003b.py --out docs/perf/baseline-004a.json
```

| 项 | 期望 |
| --- | --- |
| concurrent=4 `per_request_wall_s` | ≤1.8s（相对 2.42s 降 ≥25%） |
| HPD | `:8120/health` ok |

## 回滚

去掉 NUM_CTX 行；`num_predict=2000`；去掉 ollama.py 封顶补丁。
