# PLAN-003a：管线快赢（Vultr）

## 目标

不改泰州模型，立刻去掉双倍 LLM、修归档漏扫与双写。

## Task A1 — 术语轮默认关

`/home/dev/pdf2zh/config.toml`：

```toml
no_auto_extract_glossary = true
```

重启 `systemctl --user restart pdf2zh.service`，使 GUI 读取配置后「Enable auto term extraction」默认关。

## Task A2 — 归档会话目录 + flock

- `scripts/pdf2zh-archive-watch.py`：扫描 `PDF2ZH_ARCHIVE_SESSION_DIR`（`pdf2zh_files`）
- `run_once` 使用 `fcntl.flock` 单飞锁，防止 daemon 与 `--once` 并发双写 DT 编号
- `archive.env`：`PDF2ZH_ARCHIVE_STATE_DB=/home/dev/pdf2zh/archive/watch-state.db`

## Task A3 — 运维提示

`scripts/apply-pdf2zh-throughput.py` 在 GUI 注入简短提示：翻译进行中请勿刷新页面。

## 验收

```bash
bash scripts/verify-plan-003.sh after-a
grep -q 'no_auto_extract_glossary = true' /home/dev/pdf2zh/config.toml
journalctl --user -u pdf2zh.service --since '5 min ago' | rg -v 'Term Extraction'  # 烟测时
```

| # | 项 | 期望 |
| --- | --- | --- |
| A-V1 | config | `no_auto_extract_glossary = true` |
| A-V2 | watcher | active，日志含 `session=` |
| A-V3 | 烟测 | 日志无 `Automatic Term Extraction` |
| A-V4 | 归档 | 译完 ≤1 min 有新 `DT-*` |
