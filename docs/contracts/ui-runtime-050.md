# UI 运行时契约（PLAN-050a）

> 日期：2026-09-13  
> 施工面：**Gradio `pdf2zh_next --gui` :7860**（补丁链）  
> Vue `frontend/` **不是**生产入口（无 `dist`，Caddy 不指向它）

## 入口

| 项 | 值 |
| --- | --- |
| systemd | `pdf2zh.service`（user）`ExecStart=pdf2zh_next --gui --server-port 7860` |
| 补丁序 | [`pdf2zh-patch-order.md`](./pdf2zh-patch-order.md) 与 service `ExecStartPre` 1:1 |
| 公网 | `https://translate.qyunsgen.com` 兜底 → `127.0.0.1:7860` |
| API | `/api/v1/*` → sidecar `:8010`（PLAN-053） |
| 登录 | PLAN-040 短登录页；未登录 `/` 约 2KB |

## DOM 锚点（登录后）

| 选择器 | 角色 |
| --- | --- |
| `.qy-col-left` | 左栏：上传、翻译/取消、高级选项（语言行对用户隐藏，见 PLAN-057） |
| `.qy-col-mid` / `.qy-preview-src` | 原文画布 |
| `.qy-col-right` / `.qy-preview-dst` | 译文画布 |
| `.qy-prescan-bar` | 预扫描摘要（须来自 Manifest，见 `qyunslation.ui.manifest_view`） |
| `.qy-progress-slot` | 任务进度 |
| `.qy-050-appbar` | PLAN-050/056/057 应用栏（就绪｜方向｜模式｜帮助｜检查器）— **方向唯一用户面** |
| `.qy-050-inspector` | PLAN-057：顶栏按钮切换的检查器面板（默认隐藏；禁止 Accordion 标题条与 `translateX` 抽屉） |
| `.qy-050-help` | PLAN-057：顶栏按钮切换的帮助面板（默认隐藏） |
| `.lang-row` | 引擎用 `lang_from`/`lang_to` 容器；**对用户 `visible=False`**（由顶栏 `qy_dir` 同步） |

## Manifest → UI

字段映射见 `qyunslation.ui.manifest_view.summarize_for_ui`：

| UI | 来源 | 失败行为 |
| --- | --- | --- |
| 页数 | `len(canvases)` | 缺列表 → `unknown` / 显示 `—` |
| Figure | `summary.figure_count` | 截断/缺摘要 → `unknown`，**禁止 0** |
| Table | `summary.table_count` | 同上 |
| 状态 | issues 含 TRUNCATED/BLOCKED | `truncated` / `blocked` |
| schema | `schema_version` major=1 | 其他 major → `MANIFEST_VERSION_UNSUPPORTED` |

任务状态：`qyunslation.ui.state.TASK_STATES`。未知 → `degraded`，不得显示为完成。

## 不做

- 不把 `frontend/` Vue 当施工面
- 不解析日志猜 Figure/Table
- 向量命中不自动 `reuse=true`
