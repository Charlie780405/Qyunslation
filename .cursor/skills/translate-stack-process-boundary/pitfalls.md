# 踩坑（SK-Q004）

1. **PLAN-046d 全部嵌字改动未加载（PLAN-047）** — sidecar 启动 `2026-09-10 13:11`，改动 mtime `2026-09-12 00:24`，只重启了 `pdf2zh.service`。用户六条投诉里四条（ABC 字号、竖排旋转、F08、擦除试排）是未加载代码。正解：`deploy-translate-stack.sh` 双重启 + 指纹硬门禁。
2. **sidecar 分支 `return r.content, n, {}`（PLAN-047b）** — QC 字典硬编码空，`imgtr.json` 六条 `object_qc: []`，缺陷零告警。正解：`X-Image-QC` base64 JSON 响应头 + `qc_channel`。
3. **裸 `systemctl --user restart pdf2zh.service`** — hook 应拦截并提示改用部署脚本。
