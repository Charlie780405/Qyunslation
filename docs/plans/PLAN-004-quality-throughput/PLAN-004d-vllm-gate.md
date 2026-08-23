# PLAN-004d：同权重连续批处理（默认不做）

## 触发条件（全部满足才开）

1. 004a+b+c 完成（c 失败也算「完成」）
2. QnA 量级仍 **>12 min**
3. 翻译中 GPU0 `nvidia-smi` 利用率连续 2 min 均值 **<50%**

任一不满足：**写 WT 关闭 004d**，不装 vLLM。

## 方案（仅触发后）

- 泰州 GPU0：vLLM/SGLang 加载同一 `qwen3.6:35b-a3b`
- prefix cache；温度 0；最大输出与 004a 封顶一致
- Vultr `config.toml` 改 `openaicompatible` → 泰州兼容口

## 明确不做

- 换量化 / 换 chat 模板 / 温度非 0
- 占用 GPU1
- 未触发就预装

## 当前状态

见 `docs/walkthroughs/WT-004d-vllm-gate-closed.md`。
