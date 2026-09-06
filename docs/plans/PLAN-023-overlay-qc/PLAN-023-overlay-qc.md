# PLAN-023 图片嵌字遮罩修正与 QC 关卡

## 目标

1. 彩色框不再出现 inpaint 涂抹痕迹（按通道内点判纯色 + 矩形填充）
2. 右上「16周」不再出现多余色块（边框内缩采样）
3. 长英文不再被压成两行小字（可用区扩展 + getmetrics 行高）
4. 保存前 QC 六项，落 `.qc.json`
5. 根因写入 SK-Q002

## 改动

| 文件 | 作用 |
|------|------|
| `qyunslation/extensions/image_translate.py` | 纯色判据、一次 inpaint、可用区、QC |
| `qyunslation/app.py` | sidecar `basicConfig` |
| `.cursor/skills/image-overlay-translation/` | 铁律与踩坑 |
| `scripts/verify-plan-023.sh` | 验收 |

## 验收

`bash scripts/verify-plan-023.sh`：solid≥55/60、QC 全绿、OCR≥55、命中≥95%、回归 022。
