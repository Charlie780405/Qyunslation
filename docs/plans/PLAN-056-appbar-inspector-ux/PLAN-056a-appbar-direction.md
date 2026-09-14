# PLAN-056a：紧凑应用栏 + 方向双向同步

> 父计划：[PLAN-056](./PLAN-056-appbar-inspector-ux.md)

## 目标

应用栏一行：`就绪 | 英→中/中→英 | 快速/专业 | 帮助 | 检查器`；删除费解文案；方向与左栏语言下拉双向同步。

## 交付

改 `scripts/apply-pdf2zh-050-workbench.py` 的 `HTML_BLOCK` / 事件块：

| 控件 | 行为 |
| --- | --- |
| 状态 | 只读「就绪」 |
| `qy_dir` | Radio：`英→中` / `中→英`，`scale=0` |
| `qy_mode` | Radio：`快速` / `专业`，仍控 `qy_adv_acc.visible` |
| 帮助/检查器按钮 | `scale=0`、`size="sm"`、`min_width=72` |

方向映射（`lang_map` key）：

| Radio | lang_from | lang_to |
| --- | --- | --- |
| 英→中 | `English` | `Simplified Chinese` |
| 中→英 | `Simplified Chinese` | `English` |

其他语对不回写 `qy_dir`。

`apply_html` 必须能替换已写入的旧顶栏块（含 `# _qy_056_appbar_begin/end` 标记）。

## 完成定义

- [x] 无「方向在左侧『从…翻译』」类文案
- [x] `qy_dir.change` / `lang_from|lang_to.change` 接线存在
- [x] 二次 apply 可升级旧块
