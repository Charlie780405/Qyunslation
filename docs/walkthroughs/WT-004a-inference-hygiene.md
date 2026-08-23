# WT-004a 推理卫生

**日期：** 2026-08-23  
**状态：** 已部署（A-V1 未达目标，记录实测）

## 变更

| 项 | 内容 |
| --- | --- |
| 泰州 override | `OLLAMA_NUM_CTX=8192`、`NUM_PARALLEL=4`、`KEEP_ALIVE=-1` |
| Modelfile | `qwen3.6:35b-a3b` 增加 `PARAMETER num_ctx 8192`（原进程 `-c 262144`） |
| config.toml | `num_predict = 512` |
| ollama.py | `min(len(text)*5, 1024)` 封顶 |
| 脚本 | `scripts/deploy-taizhou-ollama-004a.sh` |

## 实测

见 `docs/perf/baseline-004a.json`：

- `observed_llama_server`：35b 加载后 `CONTEXT=8192`
- concurrent=4 `per_request_wall_s`：**2.47s**（003b 基线 2.42s；目标 ≤1.8s **未达**）
- HPD `:8120/health`：ok

## 结论

ctx/num_predict 卫生已落地；段均摊未达 25% 降幅，按纲领 **不硬冲 004d**，进入 004b。

## 回滚

`deploy-taizhou-ollama-004a.sh` 去掉 Modelfile 步骤；`num_predict=2000`；重跑 `apply-pdf2zh-throughput.py` 回滚 ollama 补丁。
