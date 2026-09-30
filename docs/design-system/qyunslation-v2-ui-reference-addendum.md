# Qyunslation Design System v2：参考站点吸收说明

日期：2026-09-30
对应计划：[PLAN-067](../plans/PLAN-067-workbench-public-cutover/README.md)

## 结论

参考站点对 Qyunslation 有帮助，但它们解决的是通用 AI 产品、动效组件或源码分发问题，不是临床翻译的监管可追溯问题。Qyunslation 采用“吸收交互语法、保留自己的临床语义和 Vue 实现”的策略：不引入 React 运行时，不把第三方注册表作为生产依赖，不用装饰性动效掩盖翻译状态。

## 参考矩阵

| 站点 | 吸收 | 转译到 Qyunslation | 排除 |
|---|---|---|---|
| [Beautiful UI](https://www.beautifului.dev/) | 阶段化处理、任务行、审批卡、差异表和可展开的处理细节 | 预检摘要、TranslationRun 阶段条、QA 决策卡、修订差异 | 不显示模型思维链、内部提示词或未经清洗的模型输出 |
| [beUI](https://beui.dev/) | 组合式控件、抽屉、选择器和短促的反馈动效 | Vue Drawer、FilterBar、Toast、保存状态和键盘反馈 | 不引入 React/Framer Motion；不购买或依赖 Pro 组件 |
| [Rare UI](https://rareui.com/) | 一个组件一个职责、源代码可控、少量具有辨识度的完成态 | 空态、成功态和非阻断装饰的候选灵感 | 不使用粒子、磁吸、3D 或持续循环动画；不复制其注册表 |
| [Transitions.dev](https://transitions.dev/) | 用过渡表达状态连续性，支持 reduced-motion | 路由、抽屉、对象检查器和阶段条的 motion token | 不在文档画布上使用模糊、位移或自动播放动画 |
| [shadcn/ui](https://ui.shadcn.com/docs) | 源码可控、组合式 API、令牌化主题、可访问状态 | 组件 API、焦点、禁用、错误、表格和抽屉的验收参考 | 不安装 React shadcn 包；Vue 组件仍以 Qyunslation tokens 为唯一视觉来源 |

## 临床翻译专用规则

1. 任务阶段必须显示阶段名称、图标和文字原因；百分比不可用时显示不确定进度，不伪造进度。
2. blocker、warning、accepted exception 和 degraded 必须同时有文字、图标和非颜色提示。
3. 源文只读；译文、术语命中、QA 和修订历史在同一对象检查器中形成可回溯链。
4. 视觉层级优先级为文档画布 > 当前任务状态 > QA/术语风险 > 技术日志；日志使用抽屉，不挤压画布。
5. 所有交互最小触控区域 44×44px；动效 120–200ms；`prefers-reduced-motion: reduce` 仅保留状态、焦点和错误反馈。
6. 真实中文医药内容必须进入视觉快照：药物名称、适应症、剂量、单位、表格、图注、长术语和 QA 文案均要覆盖换行与溢出。
7. 第三方参考只提供设计输入。复制源码前必须完成许可证、归属、供应链和依赖审查；不满足时只重写交互，不复制代码。

## 组件落地顺序

1. 先冻结 tokens、状态和可访问行为，再做视觉微调。
2. 先完成 Button、Drawer、Dialog、Tabs、DataTable、StatusBadge、ProgressStage 和 Empty/ErrorState。
3. 再落地登录、上传预检、TranslationRun、对象检查器、设置和词库联动。
4. 最后加入仅用于完成态/空态的轻量动效，并在 CI 中验证 reduced-motion、键盘流程和 axe。

## 验收记录

- 自动化：全仓库 `1010 passed, 6 skipped`；前端 type-check/build 通过。
- 公网：根路径 302 到 `/next/`，Vue 200，健康检查 200，未授权 `/api/v1/me` 401。
- 退役：Gradio upstream 不再出现在 Caddy；`pdf2zh.service` 已 disable/inactive，但包、补丁、历史产物和归档 watcher 保留用于可逆恢复。
