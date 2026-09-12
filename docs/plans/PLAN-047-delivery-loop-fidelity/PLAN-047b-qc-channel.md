# PLAN-047b QC 贯通

- sidecar `X-Image-QC` base64 JSON
- `qc_channel` 写入 imgtr.json
- `blocks>0 && object_qc==[]` → `QC_CHANNEL_BLIND`
