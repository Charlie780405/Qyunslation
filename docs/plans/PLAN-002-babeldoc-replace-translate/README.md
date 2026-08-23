# PLAN-002 BabelDOC 替换 translate.qyunsgen.com

纲领与子计划全部在本目录。WT 在 `docs/walkthroughs/`。verify 在 `scripts/verify-plan-002.sh`。

| 文件 | 作用 |
| --- | --- |
| `PLAN-002-babeldoc-replace-translate.md` | 纲领 |
| `PLAN-002a-sidecar-install.md` | 旁路安装 pdf2zh-next，不切流量 |
| `PLAN-002b-ollama-smoke.md` | 接泰州 Ollama + 资产 warmup + 样张烟测 |
| `PLAN-002c-caddy-cutover.md` | Caddy 切 `translate.qyunsgen.com` |
| `PLAN-002d-cleanup-wt.md` | 停旧进程、修 systemd、改 homepage 文案、WT |
