# PLAN-030ic：依赖探针与版本契约

> 状态：**已完成**（隶属 [PLAN-030i](./PLAN-030i-delivery-closure.md)）
> 映射：父纲领 Checkpoint D §「锁定并验证…」「无能力时 fail-fast」

## 目标

启动与 verify 阶段证明运行环境与父纲领假设一致；缺失能力在上传前失败，不靠 skip 假绿。

## 交付项

1. **版本契约文件**：仓内 `docs/contracts/versions-030.lock`（或 `qyunslation/structure/version_contract.py` 生成）记录：
   - pdf2zh-next / BabelDOC / PyMuPDF 最低兼容版本
   - Office 转换器探测命令与期望 stdout 片段
   - 核心图片解码（Pillow + 可选 libvips）能力位
2. **运行时探针**：`qyunslation/structure/runtime_probe.py`（或扩展现有 `capabilities.py`）：
   - `probe_office()`、`probe_sidecar()`、`probe_babeldoc_layout()`、`probe_image_decoders()`
   - 返回结构化 `ProbeResult(ok, reason, versions)`
3. **GUI/API 接入**：上传入口调用探针；失败时 block 并展示 reason（不进入翻译队列）。
4. **verify 脚本**：`scripts/verify-plan-030i.sh` 核心段：
   - `verify-runtime-deps.py` 对照 lock 文件
   - `SAMPLE_ROOT` 空目录时 structure 测试仍 PASS（延续 030h V6 纪律）
   - 禁止「样本不存在则 skip 整条 verify」作为唯一通过路径

## 关键文件

- `docs/contracts/versions-030.lock`（新建）
- `qyunslation/structure/runtime_probe.py`（新建）
- `scripts/verify-runtime-deps.py`（新建）
- `scripts/verify-plan-030i.sh`（新建）
- `tests/structure/test_runtime_probe.py`（新建）

## 验证

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | pytest `test_runtime_probe.py` | mock 缺失 soffice → ok=false |
| V2 | verify-plan-030i with empty SAMPLE_ROOT | PASS, blocked=0 |
| V3 | 故意 bump lock 中 PyMuPDF 版本 | verify 失败（证明门有效） |

## Out of Scope

- 容器镜像 pin（可文档引用，不在此子计划改 Dockerfile）
- Ollama/LLM 模型版本（非 030 结构链硬依赖）
