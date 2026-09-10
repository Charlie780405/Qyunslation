# PLAN-040d：刷新不杀任务

> 状态：**已完成**
> 日期：2026-09-10

## 交付

- `apply-pdf2zh-040d-refresh-keep.py`：`demo.unload` 只撤销 grace 定时器，**不** `task.cancel()`
- 手动「停止翻译」仍走 `stop_translate_file`（可取消）
- 上传中途刷新仍会中断浏览器 POST（协议限制）；登录态由 040a 保持，可重新选文件

## 验收

`bash scripts/verify-plan-040.sh` 含 040d 检查项
