# 踩坑（SK-Q004）

1. **PLAN-046d 全部嵌字改动未加载（PLAN-047）** — sidecar 启动 `2026-09-10 13:11`，改动 mtime `2026-09-12 00:24`，只重启了 `pdf2zh.service`。用户六条投诉里四条（ABC 字号、竖排旋转、F08、擦除试排）是未加载代码。正解：`deploy-translate-stack.sh` 双重启 + 指纹硬门禁。
2. **sidecar 分支 `return r.content, n, {}`（PLAN-047b）** — QC 字典硬编码空，`imgtr.json` 六条 `object_qc: []`，缺陷零告警。正解：`X-Image-QC` base64 JSON 响应头 + `qc_channel`。
3. **裸 `systemctl --user restart pdf2zh.service`** — hook 应拦截并提示改用部署脚本。
4. **译完只见「下载内容」单选、没有 File 按钮** — 自定义 Radio + `.then(_qy_export_after_translate)` 在 `translate_files` 二次 `gr.update(visible=True)` 清掉路径后把 File 藏了。回退：去掉 Radio/Checkbox，恢复上游「下载翻译（单语版）/（双语版）」；`_qy_stock_fill_downloads` 在 `demo.load` 和译完 `.then` 从 `.qy-recover.json` 回填。
