# PLAN-040b：上传完成态

> 状态：**已完成**
> 父计划：[PLAN-040](./PLAN-040-upload-auth-ux.md)

## 交付

- `scripts/apply-pdf2zh-040b-upload-settle.py`
  - `on_file_upload` 链：`show_progress="full"` 仅首段
  - `dual_payload` / prescan：`show_progress="hidden"`，不挡 File
  - 可选 JS：upload POST 200 后清除卡住的 Uploading 指示

## 验收

prescan 仍写 `qy_prescan_status`；verify 断言补丁 marker
