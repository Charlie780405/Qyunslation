# PLAN-022 嵌字配色对齐与 Skill 沉淀

## 目标

1. 彩色框内译文可见（对比度 ≥ 60）
2. 纯色遮盖替代 inpaint 花纹
3. 粗体 + 水平对齐从原图测量
4. 全屏预览不再叠两张
5. 沉淀 SK-Q002

## 改动

| 文件 | 作用 |
|------|------|
| `qyunslation/extensions/image_translate.py` | `_analyze_box_style` Otsu；纯色填充；Bold/对齐 |
| `scripts/apply-pdf2zh-viewer.py` | 整容器克隆，去嵌套双命中 |
| `.cursor/skills/image-overlay-translation/` | SK-Q002 三件套 |
| `.cursor/skills/skill-registry/registry.md` | 登记 SK-Q002 |
| `scripts/verify-plan-022.sh` | 验收 |

## 验收

`bash scripts/verify-plan-022.sh`：对比度≥60、OCR≥55、命中≥95%、registry PASS、回归 017–021。
