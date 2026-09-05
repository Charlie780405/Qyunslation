# WT-022 嵌字配色对齐与 Skill 沉淀

## 现象

流程图译后：蓝框内文字看不见或花纹涂抹；字偏细偏左；全屏预览上下两份。

## 根因

1. `vals < 120` 单侧取色把白字排除，蓝框对比度 1
2. TELEA inpaint 在纯色矩形上涂抹
3. Thin 字面 + 无条件左对齐
4. viewer 选择器同时命中 `.prose` 与内部 `img`

## 修复

Otsu 分层中位数配色 + 对比度兑底；纯色 `cv2.rectangle`；Regular/Bold + 质心对齐；整容器克隆。Skill SK-Q002 已登记。

## 验收

```bash
bash scripts/verify-plan-022.sh
bash scripts/verify-skill-registry.sh
```

## 部署

生产部署：`5ad27e9`（office + pdf2zh 已重启；verify-plan-022 23/20；SK-Q002 已 sync）。

```bash
systemctl --user restart qyunslation-office.service pdf2zh.service
```
