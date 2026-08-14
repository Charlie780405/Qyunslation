# AUDIT-001：GPU 与交付基线实测

> 日期：2026-08-14 | 机器：泰州 genscend@100.67.66.123

## GPU 拓扑

| GPU | 型号 | 显存 | 用途 |
|-----|------|------|------|
| 0 | RTX 5090 | 32GB | Ollama（`CUDA_VISIBLE_DEVICES=0`） |
| 1 | RTX 5090 | 32GB | HPD-Parsing（~25.8GB 常驻） |

## Ollama 调度

- 版本：0.30.7
- 未设置 `OLLAMA_NUM_PARALLEL` / `OLLAMA_KEEP_ALIVE`（默认）
- 冷加载 `qwen3.6:27b-ctx8k`：**10.56s**，VRAM **~16.6GB**

## 并发曲线（短 prompt × N 并行）

| concurrent | wall_s | ok |
|------------|--------|-----|
| 1 | 9.75 | 1 |
| 2 | 14.83 | 2 |
| 4 | 48.08 | 4 |
| 8 | 81.32 | 8 |

**建议 `DOCUTRANSLATE_CONCURRENT=2`**（2 并行时单请求均摊 ~7.4s，4/8 边际收益递减）。

## HPD

- `:8120/health` → ok
- benchmark 0.54s/页；本机→泰州上行 84.8 KB/s

## 结论驱动 001d

1. 默认 concurrent 30 → **2**
2. 全局翻译 Semaphore → **2**
3. 图片 OCR → **HPD**（GPU1 已部署）
4. 消除 `qwen3.6:27b` 硬编码 → 统一 `-ctx8k`
5. `presence_penalty 1.5`：A/B 术语一致，但 0 更少废话；建议 Modelfile 变体 `presence_penalty 0`
