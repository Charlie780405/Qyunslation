# WT-003：翻译吞吐加速（保质量）

对应 PLAN-003。执行日期：2026-08-23。

## 执行摘要

- **003a**：默认关自动抽术语、归档扫 `pdf2zh_files` + flock、GUI 运维提示
- **003b**：35b-a3b 并发曲线 1/2/4，`OLLAMA_NUM_PARALLEL=4`，Vultr `qps=4`
- **003c**：浏览器 unload 取消进行中的翻译任务

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `docs/plans/PLAN-003-translate-throughput/*` | 纲领 + 003a/b/c |
| `scripts/verify-plan-003.sh` | 分阶段断言 |
| `scripts/apply-pdf2zh-throughput.py` | unload + 提示补丁 |
| `scripts/benchmark-ollama-003b.py` | 泰州并发曲线 |
| `scripts/deploy-taizhou-ollama-003b.sh` | system ollama override |
| `scripts/pdf2zh-archive-watch.py` | session 目录 + flock |
| `scripts/pdf2zh.service` | ExecStartPre apply 补丁 |
| `/home/dev/pdf2zh/config.toml` | `no_auto_extract_glossary=true`, `qps=4` |
| `/home/dev/pdf2zh/archive.env` | SESSION_DIR + LOCK_FILE |
| `docs/perf/baseline-003b.json` | 1/2/4 并发实测 |
| 泰州 `/etc/systemd/system/ollama.service.d/override.conf` | `OLLAMA_NUM_PARALLEL=4` |

## 验证结果

| # | 项 | 结果 | 备注 |
| --- | --- | --- | --- |
| V1 | verify-plan-003 after-a | 15/15 PASS | |
| V2 | verify-plan-003 after-b | 16/16 PASS | 含 baseline JSON |
| V3 | verify-plan-003 after-c | 15/15 PASS | unload 补丁 |
| V4 | HPD health | ok | `:8120` 未回归 |

## perf 快照（baseline-003b）

| concurrent | per_request_wall_s |
| --- | --- |
| 1 | 3.11 |
| 2 | 2.65 |
| 4 | 2.42 |

推荐：`OLLAMA_NUM_PARALLEL=4`，`qps=4`。

## 已知限制

- unload 取消为单租户全局任务指针；多用户同时翻译时可能互相取消
- 泰州 ollama 需 sudo 改 system drop-in（非 user unit）
- `DT-2026-0003` 为补归档撞车重复项，未在本 PLAN 清理

## 遗留问题与下阶段输入

- [ ] 手动 sudo：`sudo systemctl disable --now docutranslate.service`（PLAN-002 遗留）
- [ ] 荃信白牌 → 后续 PLAN
- [ ] 手动术语表 `--glossaries` 接入 → 可选
