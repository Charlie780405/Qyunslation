# WT-021 图片翻译丢字修复与预览查看器

## 现象

流程图 JPG 中译英 / 英译中均出现大面积文字未翻译或丢失；预览无法放大旋转。

## 根因

1. HPD 把整张流程图标成 `image` 块，内部零 OCR（实测仅 2 框脚注）。
2. `/no_think` 对 qwen3.6 无效，thinking 烧光 `num_predict=2000`，`content` 为空。
3. 先 inpaint 全部框再条件绘制 → `trans` 空时净删字。

## 修复

- RapidOCR 主路径（同图 60 框 / 2s），HPD 回退
- `think: false` + 25 条分批 + 缺失单条重试
- 只擦将重绘的框；缺译保留原像素
- 字号按框宽二分 + 自动换行；返回真实绘制数
- docx / custom_api / image_replace 透传 `to_lang`
- `apply-pdf2zh-viewer.py`：内嵌工具条 + 全屏（img / HTML / PDF canvas）

## 验收

```bash
bash scripts/verify-plan-021.sh
# OCR_BOXES=60 HIT=60/60 DRAWN=60 → 20 passed, 0 failed
```

浏览器：硬刷新后上传流程图，中译英应覆盖阶段标题与给药标签；预览悬停出现工具条，可缩放/旋转/全屏。

生产部署：`c76302f`（office + pdf2zh 已重启；verify-plan-021 20/20；viewer 补丁已写入 gui.py）。

## 部署

```bash
cp scripts/pdf2zh.service ~/.config/systemd/user/pdf2zh.service
systemctl --user daemon-reload
systemctl --user restart qyunslation-office.service pdf2zh.service
```
