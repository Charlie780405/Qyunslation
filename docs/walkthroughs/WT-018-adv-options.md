# WT-018 高级选项展开修复与位置下移

## 目标

修复左栏 `flex-wrap: wrap` 导致高级选项展开后内容与翻译按钮「消失」；将高级选项移到翻译/取消下方并内部滚动；隐藏「保存设置」。

## 部署

- feat: `f72ad23`
- merge main: `14d6ec4`

```bash
bash scripts/verify-plan-017.sh
bash scripts/verify-plan-017b.sh
bash scripts/verify-plan-018.sh
systemctl --user daemon-reload
systemctl --user restart pdf2zh.service
```

## 浏览器核对

1. **折叠态**：翻译/取消在「高级选项」上方；左栏 `flex-wrap: nowrap`。
2. **展开态**：手风琴在按钮下方向下展开；内容 `max-height: 400px` + `overflow-y: auto`；翻译/取消仍在左栏可视区内，不换列消失。
3. 「保存设置」不可见；页码范围/术语表/水印/忽略缓存/仅输出翻译页/界面语言仍可用。

## 已核对（2026-09-05）

- verify-plan-017: 18/18
- verify-plan-017b: 13/13
- verify-plan-018: 9/9
- 浏览器：折叠/展开均通过；`flexWrap=nowrap`；展开后 action-row 仍在左栏内；手风琴内容 `overflow-y: auto`
