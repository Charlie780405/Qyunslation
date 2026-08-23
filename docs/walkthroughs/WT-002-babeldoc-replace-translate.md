# WT-002：BabelDOC 替换 translate.qyunsgen.com

对应 PLAN-002。执行日期：2026-08-23。

## 执行摘要

- **目标**：`translate.qyunsgen.com` 从 Qyunslation（:8010）换成 PDFMathTranslate-next / BabelDOC（:7860）
- **homepage href 不变**；卡片文案改为「翻译 BabelDOC」
- **引擎**：原生 Ollama `http://100.67.66.123:11434`，模型 `qwen3.6:35b-a3b`
- **安装**：`uv tool install --python 3.12 pdf2zh-next`（2.9.0，babeldoc 0.6.2）
- **常驻**：`systemctl --user` 的 `pdf2zh.service`（非 `/etc/systemd`，因无 passwordless sudo）

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `docs/plans/PLAN-002-babeldoc-replace-translate/*` | 纲领 + 002a–d 详细子计划 |
| `scripts/verify-plan-002.sh` | 分阶段拓扑断言 |
| `scripts/deploy-pdf2zh-cutover.sh` | Caddy reload 切流脚本 |
| `scripts/pdf2zh.service` | user systemd unit 模板 |
| `/home/dev/qyunsgen/config/Caddyfile-production-public` | translate 块 `8010`→`7860` |
| `/home/dev/homepage/config/services.yaml` | 卡片标题/描述 |
| `/home/dev/pdf2zh/config.toml` | Ollama + 公网 GUI 限制（仓库外） |
| `~/.config/systemd/user/pdf2zh.service` | 已 enable |

## 验证结果

| # | 项 | 结果 | 备注 |
| --- | --- | --- | --- |
| V1 | verify baseline | 6/6 PASS | 切流前 |
| V2 | verify after-a | 6/6 PASS | uv 安装 |
| V3 | verify after-b | 6/6 PASS | 7860 + 公网仍 Qyunslation |
| V4 | 1 页 PDF 烟测 | PASS | mono+dual 约 121s；样张 Seeking Alpha 新闻 PDF 第 1 页 |
| V5 | verify after-c | 7/7 PASS | 公网非 Qyunslation 标题 |
| V6 | verify after-d | 见下 | 8010 已停 |
| V7 | pdf2zh user service | active + enabled | |

烟测输出：

- `/home/dev/pdf2zh/out/page1.no_watermark.zh.mono.pdf`（306KB）
- `/home/dev/pdf2zh/out/page1.no_watermark.zh.dual.pdf`（404KB）

## 部署记录

| 项 | 值 |
| --- | --- |
| pdf2zh-next | 2.9.0 |
| babeldoc | 0.6.2 |
| Caddy | `caddy reload`（非 restart，符合生产 hook） |
| 切流 | translate → `127.0.0.1:7860` |

## 回归确认

- `table.qyunsgen.com` → 307（正常）
- `knowledge.qyunsgen.com` → 401（需 basic auth，服务在）
- homepage `href` 仍为 `https://translate.qyunsgen.com`

## 已知限制

- **仅 PDF**：Word/图嵌字/多格式不再经此入口
- **UI**：Gradio 默认界面，非荃信白牌
- **`docutranslate.service`**：仍 enabled 但 `203/EXEC`（需 sudo 执行 `systemctl disable --now`）
- **CLI 烟测**：须用 `smoke-config.toml`（`gui=false`），勿与 `--config-file` 中 `gui=true` 混跑

## 遗留问题与下阶段输入

- [ ] 手动 sudo：`sudo systemctl disable --now docutranslate.service` → 002d 卫生
- [ ] 可选：荃信白牌 / `--auth-file` 登录墙 → 后续 PLAN
- [ ] 术语表 CSV 迁入 pdf2zh `--glossaries` → 后续

## 回滚

1. Caddy translate 块改回 `127.0.0.1:8010`，`docker exec qyunsgen-caddy caddy reload --config /etc/caddy/Caddyfile`
2. `/home/dev/qyunslation` 拉起 `.venv/bin/qyunslation -i --host 0.0.0.0 --port 8010`
3. `systemctl --user stop pdf2zh.service`
