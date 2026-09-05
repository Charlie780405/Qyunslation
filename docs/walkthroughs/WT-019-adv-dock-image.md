# WT-019 高级选项吸底 + 图片翻译下载与中译英

## 目标

左栏翻译/取消与高级选项 sticky 吸底；图片导出可下载；PDF/DOCX/图片支持中英双向。

## 部署

- feat: （见 commit）
- merge main: （见 commit）

```bash
bash scripts/verify-plan-017.sh
bash scripts/verify-plan-017b.sh
bash scripts/verify-plan-018.sh
bash scripts/verify-plan-019.sh
systemctl --user daemon-reload
systemctl --user restart qyunslation-office.service
systemctl --user restart pdf2zh.service
```

## 已核对（2026-09-05）

### 布局

- verify-plan-017/017b/018/019 全过
- 浏览器：`action-row` / `.qy-adv-acc` 均为 `position: sticky`；展开后 `--qy-dock-h` 从 58px 更新为实际高度；按钮与手风琴始终在左栏可视区内

### 图片

- `_build_export_map` 独立 `ImageOverlayWorkflow` 分支 → 日志出现「成功生成 image 文件」
- `FileType` / `MEDIA_TYPES` 增加 `image` → `/service/download/.../image` 返回 200 JPEG（约 400KB）
- sidecar `to_lang=English` / `简体中文` 均可完成

### DOCX

- sidecar `to_lang=English`：译文段落为
  - `This is a Chinese test paragraph used to verify Chinese-to-English translation.`
  - `Clinical trial protocol design.`

### PDF

- BabelDOC `base_translator.prompt` 使用动态 `{self.lang_out}`；throughput 跳过启发式含 `zh→en` 分支；ocr-base / doc_profile 无语言方向假设。本 PLAN 无 PDF 代码改动。

### 卫生

- `_qy_run_office_sidecar_task` 从 64 份收敛为 1 份；`gui.py` 约 12683 → ~6100 行
