# PLAN-002a：旁路安装 pdf2zh-next

> 父纲领：`PLAN-002-babeldoc-replace-translate.md`
> 状态：已完成 | 2026-08-23

## 目标

在本机用官方 uv 路径装好 PDFMathTranslate-next，写成 systemd unit，默认 **不 enable、不切流**。Qyunslation 继续服务 `translate.qyunsgen.com`。

## 父纲领进度

| 子计划 | 状态 |
| --- | --- |
| 002a | 本文件 |
| 002b–002d | 未开始 |

## 依赖 / 前置条件

- 官方：`uv tool install --python 3.12 pdf2zh-next`（https://pdf2zh-next.com/getting-started/INSTALLATION_uv.html）
- Python 约束：3.10–3.12（官方）
- 本机已有 `uv`；PATH 需含 `~/.local/bin`
- 端口 **7860** 必须空闲

## Out of Scope

- Caddy / homepage / 停 qyunslation
- warmup、真译、拉模型
- Docker 镜像
- clone BabelDOC 当生产入口

## 关键决策

| # | 决策 | 理由 |
| --- | --- | --- |
| A1 | `uv tool install` | 官方自托管包是 pdf2zh-next |
| A2 | 工作目录 `/home/dev/pdf2zh/` | 与 qyunslation 仓库分离 |
| A3 | unit 写成 `pdf2zh.service`，002a 只 `daemon-reload`，**不 enable** | 旁路；002b 再常驻 |

## Task A1 — 容量与端口（不足则中止）

```bash
df -h / /home
ss -lntp | rg '7860|8010'
uv --version
echo "$PATH" | rg '\.local/bin'
```

**Acceptance：**
- [ ] `/` 与 `/home` 可用空间均 ≥5G
- [ ] `7860` 空闲
- [ ] `8010` 仍是 `qyunslation`
- [ ] `uv --version` 可用

**Verify：** 输出记入本文件 §附录。

## Task A2 — 官方安装

```bash
uv tool install --python 3.12 pdf2zh-next
export PATH="$HOME/.local/bin:$PATH"
pdf2zh_next --version
pdf2zh_next --help | tee /home/dev/pdf2zh/help.txt
```

**Acceptance：**
- [ ] `pdf2zh_next --version` 退出 0
- [ ] help 含 `--gui` / `--server-port` / `--config-file` / `--ollama`
- [ ] 未改 `/home/dev/qyunslation` 业务代码
- [ ] 公网标题仍是「荃信翻译 · Qyunslation」

**Verify：** `curl -sS http://127.0.0.1:8010/ | rg -o '<title>[^<]+</title>'`

## Task A3 — 目录与默认配置副本

```bash
mkdir -p /home/dev/pdf2zh/{out,sample}
```

- 默认配置在 `~/.config/pdf2zh/`，**不改 `default/`**
- 首次 `--help` 后，把生成的默认文件复制为 `/home/dev/pdf2zh/config.toml`（002b 再改引擎节）
- 在 help 里查 `--server-name`：有则 unit 绑 `127.0.0.1`；无则 002b 仅 Caddy 暴露

## Task A4 — systemd 草稿（不 enable、不常驻）

`/etc/systemd/system/pdf2zh.service`：

```ini
[Unit]
Description=PDFMathTranslate-next (BabelDOC) WebUI for translate.qyunsgen.com
After=network.target

[Service]
Type=simple
User=dev
WorkingDirectory=/home/dev/pdf2zh
Environment=PATH=/home/dev/.local/bin:/usr/bin:/bin
ExecStart=/home/dev/.local/bin/pdf2zh_next --gui --server-port 7860 --ui-lang zh --config-file /home/dev/pdf2zh/config.toml --disable-config-auto-save --disable-gui-sensitive-input --enabled-services Ollama
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemd-analyze verify /etc/systemd/system/pdf2zh.service
sudo systemctl daemon-reload
systemctl is-enabled pdf2zh.service   # 必须 disabled
```

## 验证清单

| # | 步骤 | 预期 |
| --- | --- | --- |
| A-V1 | `pdf2zh_next --version` | 有版本号 |
| A-V2 | `bash scripts/verify-plan-002.sh after-a` | 全 PASS |
| A-V3 | `ss -lntp \| rg 7860` | 无长期监听 |

## 回滚

`uv tool uninstall pdf2zh-next`；删 unit 与 `/home/dev/pdf2zh`；不碰 Caddy。

## 附录（执行记录）

| 项 | 值 |
| --- | --- |
| 执行日期 | 2026-08-23 |
| pdf2zh_next 版本 | 2.9.0 |
| 磁盘 `/` 可用 | 275G |
| 磁盘 `/home` 可用 | 275G |
