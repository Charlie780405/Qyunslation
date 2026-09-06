# WT-023 图片嵌字遮罩修正与 QC 关卡

## 交付

- 按通道内点 + 边框内缩判纯色；彩色框改矩形填充
- 非纯色邻域取色 + 全图一次 inpaint；未译框像素回贴
- `_available_box` + `getmetrics` 行高，长英文可读
- `_qc_report` 六项 → `<out>.qc.json`；sidecar `basicConfig`
- SK-Q002 铁律 / 踩坑更新；`verify-plan-023.sh` PASS=27

## 部署

- 分支：`feat/plan-023-overlay-qc`
- 合并：`--no-ff` → `main`
- 服务：`pdf2zh.service` + `qyunslation-office.service` 已重启
- 生产哈希：`8f809ca`
