# PLAN-002：用 BabelDOC 替换 translate.qyunsgen.com

> 状态：已完成 | 日期：2026-08-23
> 工作区：`/home/dev/qyunslation`（Vultr）

## 目标

把 homepage 卡片「翻译 Qyunslation」所指向的 `https://translate.qyunsgen.com` 从当前 Qyunslation（原 DocuTranslate 白牌，`:8010`）换成 **PDFMathTranslate-next（内嵌 BabelDOC）**，域名与 homepage 链接不变。

## 实测基线（2026-08-23，只读，未安装）

```
homepage.qyunsgen.com
  → Caddy → 127.0.0.1:6120（qyunsgen-homepage）
  → 卡片 href = https://translate.qyunsgen.com

translate.qyunsgen.com
  → Cloudflare Proxied
  → qyunsgen-caddy（host 网络）
  → reverse_proxy 127.0.0.1:8010
  → /home/dev/qyunslation/.venv/bin/qyunslation -i --port 8010
  → 页面标题「荃信翻译 · Qyunslation」
  → LLM：Ollama qwen3.6:35b-a3b @ 100.67.66.123:11434
```

- `translate.qyunsgen.cm`：无解析（NXDOMAIN）。目标域名是 **`.com`**。
- `/home/dev/docutranslate` 已删除；`docutranslate.service` 仍指向该路径，`203/EXEC` 死循环。
- 现网 `qyunslation` 进程 PPID=1，**没有** `qyunslation.service`。
- Caddy 站点块 SSOT：`/home/dev/qyunsgen/config/Caddyfile-production-public`（共享主机反代，改它=改全机 `*.qyunsgen.com`）。

## 父纲领进度

本 PLAN 为新纲领，不挂在 PLAN-001 下。PLAN-001（Qyunslation 质量/GPU）对**现网入口**被本计划取代；仓库代码保留，001 未完成项不在本期消化。

| 编号 | 名称 | 状态 | 备注 |
| --- | --- | --- | --- |
| 002a | 旁路安装 | 已完成 | pdf2zh-next 2.9.0 |
| 002b | Ollama + 烟测 | 已完成 | 1 页 mono+dual |
| 002c | Caddy 切流 | 已完成 | reload 7860 |
| 002d | 清理 + WT | 已完成 | 8010 已停；docutranslate 待 sudo disable |

## 上一子计划缺口分析

来源：PLAN-001 无 WT；本会话只读勘察。

| 缺口 | 归并 |
| --- | --- |
| `docutranslate.service` 空转 | →002d |
| qyunslation 无 systemd | →002d（停掉即可，不补旧 unit） |
| PLAN-001 质量门禁未完成 | 关闭（现网入口替换后不再作为生产路径） |
| 归档 `DT-2026-*` 只读保留 | 本期不迁、不删 |

## 依赖 / 前置条件

- 官方：BabelDOC 是库；**自托管 + WebUI 走 PDFMathTranslate-next**。BabelDOC CLI「mainly for debugging」，官方不提供终端用户技术支持。
  - https://funstory-ai.github.io/BabelDOC/
  - https://github.com/funstory-ai/BabelDOC
- 官方安装：Linux 推荐 Docker；另有 uv：`uv tool install --python 3.12 pdf2zh-next`，WebUI `pdf2zh_next --gui`，默认 `http://localhost:7860/`。
  - https://pdf2zh-next.com/getting-started/INSTALLATION_docker.html
  - https://pdf2zh-next.com/getting-started/INSTALLATION_uv.html
  - https://pdf2zh-next.com/getting-started/USAGE_webui.html
  - https://pdf2zh-next.com/advanced/advanced.html
- pdf2zh-next 有原生 **Ollama** 引擎（`ollama_host` + `ollama_model`，走 Ollama 原生 API，**不要** `/v1`）。OpenAI 兼容层 `.../v1` 仅作烟测失败回退。
- 现网 Ollama 在泰州 Tailscale `100.67.66.123:11434`，**不是**本机 `11434`。官方 Docker 的 `host.docker.internal:11434` **不适用于本机拓扑**。
- 公网部署官方警告：项目未经专业安全审计；公开服务须 `disable_gui_sensitive_input` + `disable_config_auto_save`。
- 共享 Caddy：改 bind-mount 单文件后必须 `docker restart qyunsgen-caddy`（reload 会读到旧 inode）。见 `local-document-translation` Skill。

## Out of Scope

- 把 BabelDOC 嵌进 Qyunslation 源码（AGPL-3.0 会污染 MPL-2.0 仓库）
- 保留 docx / xlsx / md / json / epub / srt / 图片嵌字 / MinerU 作为**同一入口**能力
- 荃信白牌重做 pdf2zh Gradio UI
- 删除 `/home/dev/qyunslation` 仓库或归档 `DT-2026-*`
- 改 homepage 的 href（域名必须保持 `translate.qyunsgen.com`）
- 用 Immersive Translate 在线版 / 外发 PDF
- 改泰州 Ollama 模型或 GPU 调度（沿用 `qwen3.6:35b-a3b`）

## 关键决策

| # | 决策 | 理由 |
| --- | --- | --- |
| D1 | 替换对象是 Caddy 后面的 `:8010` 进程，不是 homepage 链接 | 已实测公网 HTML = 本机 Qyunslation |
| D2 | 运行时用 **pdf2zh-next**，不单独对外暴露 `babeldoc` CLI | 官方自托管入口 |
| D3 | **uv tool + systemd**，不用 Docker | 官方有 uv 路径；Ollama 在 Tailscale，Docker 默认示例会指错；与现网「宿主机进程 + Caddy」一致 |
| D4 | 先占 **127.0.0.1:7860** 旁路，确认后再改 Caddy | 切流前 Qyunslation 继续服务 |
| D5 | 翻译引擎：原生 Ollama → `http://100.67.66.123:11434`，模型 `qwen3.6:35b-a3b`；OpenAI `/v1` 仅回退 | 官方 `OllamaSettings`；与 Qyunslation 的 OpenAI 兼容层不同 |
| D6 | 公网 GUI：只开 `Ollama` 服务；关敏感输入自动保存 | 官方「Deployment as a public services」 |
| D7 | 水印 `no_watermark`；Qwen 用 `/no_think` 系统提示 | 内网使用；官方 Qwen3 建议 |
| D8 | QPS 从保守值起步（≤2） | 现网 `concurrent=2`，避免打满泰州 GPU |

## 子计划

| 编号 | 文件 | 交付物 | 切流？ |
| --- | --- | --- | --- |
| 002a | `PLAN-002a-sidecar-install.md` | `pdf2zh_next --version`；unit 未 enable | 否 |
| 002b | `PLAN-002b-ollama-smoke.md` | warmup + 1 页 PDF 成功 | 否 |
| 002c | `PLAN-002c-caddy-cutover.md` | `translate.qyunsgen.com` → `:7860` | **是** |
| 002d | `PLAN-002d-cleanup-wt.md` | 停 8010、禁旧 unit、homepage 文案、WT | 已切 |

## 变更文件清单（全系列预估）

| 路径 | 操作 | 用途 |
| --- | --- | --- |
| `docs/plans/PLAN-002-babeldoc-replace-translate/*` | 新增 | 本纲领/子计划 |
| `scripts/verify-plan-002.sh` | 新增 | 拓扑 + 健康断言 |
| `/etc/systemd/system/pdf2zh.service` | 新增 | 常驻 WebUI（002a/b） |
| `/home/dev/pdf2zh/config.toml` | 新增 | 公网 GUI + Ollama（仓库外，不入库密钥） |
| `/home/dev/qyunsgen/config/Caddyfile-production-public` | 修改 | `8010` → `7860`（002c） |
| `/home/dev/homepage/config/services.yaml` | 修改 | 卡片 description 改为 BabelDOC（href 不变） |
| `/etc/systemd/system/docutranslate.service` | disable | 002d |

## 验证清单

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | `bash scripts/verify-plan-002.sh` | 按阶段断言（002a 不要求公网已切） |
| V2 | `curl -sS http://127.0.0.1:7860/` | 200，Gradio/pdf2zh WebUI |
| V3 | 1 页英文 PDF → 中文 mono + dual | 版式可辨，非 markdown 丢失排版 |
| V4 | `curl -sSI https://translate.qyunsgen.com/` | 切流后标题不再是「荃信翻译 · Qyunslation」 |
| V5 | homepage 卡片 href 仍是 `https://translate.qyunsgen.com` | 点击进新 UI |
| V6 | `systemctl is-active pdf2zh.service` | active；`docutranslate.service` disabled |
| V7 | `ss -lntp` `:8010` | 切流后无 qyunslation |

## 回滚预案

1. Caddy `reverse_proxy` 改回 `127.0.0.1:8010`，`docker restart qyunsgen-caddy`。
2. 在 `/home/dev/qyunslation` 重新拉起：`.venv/bin/qyunslation -i --host 127.0.0.1 --port 8010`。
3. `systemctl stop pdf2zh.service`（可选，避免双开）。
4. 不回滚数据库（无）。

## 影响范围

- 用户可见：同一 URL，UI 从 Qyunslation 变为 pdf2zh Gradio；**只接受 PDF**。
- 共享 Caddy、homepage 文案、泰州 Ollama 负载。
- 许可证：pdf2zh/BabelDOC 为 AGPL，作为独立进程运行，不链进 Qyunslation 包。

## 累积缺口登记表

| 缺口 | 状态 | 归并 |
| --- | --- | --- |
| 荃信白牌 UI | 后续 | 未开编号 |
| Word/图嵌字入口 | 不做 | 关闭（本入口不再提供） |
| 登录墙（`--auth-file`） | 可选 | 若公网暴露需评估 → 后续 |
