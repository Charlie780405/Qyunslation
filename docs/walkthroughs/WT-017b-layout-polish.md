# WT-017b 布局打磨

## 目标

进度条迁左栏（上传框下、「翻译选项」上，空闲零占位）；「当前文档」迁左栏；中右预览框顶底对齐；页脚横贯中+右居中。

## 部署

- feat: （见 commit）
- merge main: （见 commit）

```bash
bash scripts/verify-plan-017.sh
bash scripts/verify-plan-017b.sh
systemctl --user daemon-reload
systemctl --user restart pdf2zh.service
```

## 浏览器核对

1. 空态：中栏「上传文件后在此预览原文」与右栏「翻译完成后在此显示译文」框顶底对齐、同宽同高；左栏无进度条占位。
2. 「当前文档」下拉在左栏上传框下方；中栏仅「原文」标题 + 预览框。
3. 模拟/真实翻译中：进度条出现在「当前文档」与「翻译选项」之间，不撑破布局。
4. 页脚为横贯中+右的细条，正中 logo +「Qyunslation · 荃信生物 © 2026」。
5. 多页 PDF：一侧翻页/改页码，另一侧同步到同一页；面板内滚动也按比例同步。

## 已核对（2026-09-05）

- verify-plan-017: 18/18
- verify-plan-017b: （含页码联动）
- 浏览器：中右栏等高；空态框同高；进度空闲 `display:none`，激活后位于「当前文档」与「翻译选项」之间；页脚可见于视口内（logo + 版权横贯中+右）；`_qy_page_sync` 已注入
