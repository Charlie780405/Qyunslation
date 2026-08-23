# PLAN-003c：刷新/断开即取消任务

## 目标

浏览器刷新或关闭标签时，取消服务端进行中的翻译，避免 Abstract 式僵尸占满泰州 GPU；已写完的 PDF 仍由 watcher 归档。

## Task C1 — Gradio unload 钩子

`scripts/apply-pdf2zh-throughput.py` 在 `pdf2zh_next/gui.py` 的 `cancel_btn.click` 之后注入：

```python
        demo.unload(
            stop_translate_file,
            inputs=[state],
        )
```

复用已有 `stop_translate_file`（内部 `current_task.cancel()`）。

## Task C2 — systemd 启动前 apply

`scripts/pdf2zh.service` 的 `ExecStartPre`：

```ini
ExecStartPre=/usr/bin/python3 /home/dev/qyunslation/scripts/apply-pdf2zh-throughput.py
```

每次启动 pdf2zh 前确保补丁在位（uv 升级后自动重打）。

## 验收

| # | 项 | 期望 |
| --- | --- | --- |
| C-V1 | gui.py | 含 `demo.unload` + `stop_translate_file` |
| C-V2 | 刷新后新 PDF | 30s 内日志出现 `Parse`（非旧文件名） |
| C-V3 | 已完成 PDF | Vault 仍可检索 |

## 限制

- unload 仅对**当前浏览器会话**的 State 生效；多用户同时用时各会话独立
- 取消后进行中段落丢弃，需重新点翻译
