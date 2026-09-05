# WT-020 上传/翻译永久转圈

## 现象

上传图片后界面长时间转圈，计时器累加到 200s 以上，服务端无任何日志、
office sidecar 无请求。刷新后重试仍然复现。

## 定位过程

1. 服务端排查：`journalctl` 零异常；同一张图纯 API 30s、公网浏览器 17s 完成，
   下载正常 → 后端健康。
2. 注意到成功的上传同样不打日志，故「零日志」不能证明回调没跑。
3. 在受控浏览器里复现后，用 `performance.getEntriesByType('resource')` 取回时序：
   - `queue/data` 单条传输 **789855 字节耗时 27s**（≈29KB/s）
   - 其后 `queue/join` 从 550ms 劣化到 **16.6s**
4. 789855 正是 590KB 图片 base64 后的长度 → 定位到 `_qy_preview_payload` 内联 data URL。

## 修复

| 补丁 | 作用 |
|------|------|
| `apply-pdf2zh-preview-url.py` | 预览改走 `/gradio_api/file=`；DOCX 内联 data URI 落盘外置 |
| `apply-pdf2zh-css-has-fix.py` | 嵌套 `:has()` 非法致整条规则被丢弃，空态提示无法隐藏 |
| `apply-pdf2zh-glossary-encoding.py` | `chardet.detect()` 返回 None 引发的 TypeError / StopIteration |
| `apply-pdf2zh-stale-guard.py` | app_id 漂移与回执丢失时给出明确文案 |
| `apply-pdf2zh-no-store.py` | index.html / config 禁缓存，旧组件树不再残留 |
| `apply-pdf2zh-left-dock.py` | 吸底 JS 去掉 body MutationObserver 与 400ms 轮询 |

## 验收

```bash
bash scripts/verify-plan-017.sh    # 18/18
bash scripts/verify-plan-017b.sh   # 13/13
bash scripts/verify-plan-018.sh    # 9/9
bash scripts/verify-plan-019.sh    # 22/22
bash scripts/verify-plan-020.sh    # PASS
cp scripts/pdf2zh.service ~/.config/systemd/user/pdf2zh.service
systemctl --user daemon-reload && systemctl --user restart pdf2zh.service
curl -sI https://translate.qyunsgen.com/ | grep -i cache-control   # no-store
```

浏览器实测：预览载荷 789855 B → 3031 B；图片中译英 20s 出结果；
空态提示 `display: none`；无误报横幅。

## 注意

- `apply-pdf2zh-brand.py` 每次运行都重写 `gui.py`，会冲掉后续 CSS/JS 块，
  由链中后续补丁重新贴回。链尾状态正确，但日志里会看到多个 “patched”。
  新增补丁必须排在链尾，且自身要能自愈替换旧片段。
- 客户端上传带宽实测仅 11–13 KB/s，576KB 图片上传本身需 45–70s，
  属链路问题，不在本次范围内。
