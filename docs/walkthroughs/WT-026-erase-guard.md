# WT-026 擦除保护与竖向锚定复位

## 做了什么

- 纯色填充改为 `_fill_band`（只填非线状文字行带），并 `_line_guard_mask` 保护贯穿线；全部擦除后回贴各框文字带外原图像素，挡住邻框越界。
- 竖向锚定改为三段式（实心彩色居中 / 能放下居中 / 放不下顶对齐），`anchors.vertical_mode` 写入 QC。
- QC 新增 C10（图元损伤），纳入 `QC_STRICT`。
- SK-Q002 重构：通用原则四条 + 新图接入自检清单；pitfalls #26/#27；reference 补 ENV 与竖向表。

## 怎么验

```bash
bash scripts/verify-plan-026.sh
```

期望：括号线 `y=116-117` 非白存活率 ≥90%；#5/#6/#7/#8 中心偏移 ≤3px；QC 无 C8/C9/C10；回归 025 通过。

## 部署

main `5a1ff3c`，已重启 `qyunslation-office.service`（active），`https://translate.qyunsgen.com/` 返回 200。
`verify-plan-026.sh` PASS=23 FAIL=0；括号线存活 100%；周数中心偏移 ≤0.5px。
