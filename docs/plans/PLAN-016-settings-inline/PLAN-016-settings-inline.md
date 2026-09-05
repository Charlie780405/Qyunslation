# PLAN-016 设置项内联左栏与配置入口收敛

## 目标

填补翻译页左栏下方空白：把真正有用的配置搬到左栏（文档类型模板常驻 + 「高级选项」折叠）；取消 ⚙️ 独立入口。其余控件永久隐藏但保留为参数载体，避免打乱 `build_ui_inputs` 位置映射。

## 必要性结论（摘要）

| 类别 | 代表项 | 处理 |
|------|--------|------|
| 模板覆盖 | primary_font_family、split_short_lines、disable_rich_text_translate… | 隐藏 |
| HPD 强制 | ocr_workaround、skip_scanned_detection… | 隐藏 |
| 单引擎死项 | service、term_* | 隐藏 |
| 运维参数 | QPS/线程、system prompt、ollama host… | 隐藏（config.toml） |
| BabelDOC 调参 | formula regex、IOU… | 隐藏 |
| 下载区已取代 | no_mono / no_dual / dual_* | 隐藏 |
| 有价值 | 文档类型、页码、术语表、忽略缓存、水印、界面语言、保存 | **前移左栏** |

## 改动

| 文件 | 内容 |
|------|------|
| 补丁 | `scripts/apply-pdf2zh-settings-inline.py` |
| 服务 | `scripts/pdf2zh.service`（末位 ExecStartPre） |
| 验收 | `scripts/verify-plan-016.sh`、`docs/walkthroughs/WT-016-settings-inline.md` |

## 左栏目标结构

```
语言行 → 文档类型模板 → ▸高级选项 → 下载区 → [翻译][取消]
```

高级选项内：页码范围、仅输出译文页、术语表、忽略缓存、水印、界面语言、保存设置。

## 验收

```bash
bash scripts/verify-plan-016.sh
systemctl --user restart pdf2zh.service
```

并按 WT-016 做浏览器核对。
