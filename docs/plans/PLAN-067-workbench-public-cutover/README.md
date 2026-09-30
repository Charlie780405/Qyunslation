# PLAN-067：Qyunslation Authentik → Vue `/next` 公网灰度与 Gradio 退役评估

状态：**已完成 · Vue 正式入口已部署，Gradio 服务已可逆退役**

## 目标

在不破坏现有 Gradio 根入口、旧任务和下载能力的前提下，完成 Authentik OIDC、BFF 会话、Vue `/next` 公网灰度，并以完整自动化、真实端到端和回滚证据评估 Gradio 是否进入受控退役阶段。24 小时观察不再作为硬门槛，但不得以未验证的功能或不可回滚的卸载替代测试。

## 已冻结决策

- Vue `/next` 是正式目标 UI；Gradio 只作为迁移期回退入口。
- 登录只使用公司 SSO；不提供用户名/密码备用表单。
- 灰度使用 Authentik 试点组 `qyunslation-vue-beta`，服务端映射为 `workbench_v2` capability。
- 观察窗口作为补充证据，不再是用户确认的硬门槛；完整验收、真实任务和回滚证据为退役前置条件。
- BFF 唯一回调为 `https://translate.qyunsgen.com/auth/callback`。
- 浏览器只持有 HttpOnly BFF 会话，不持有 OIDC access/refresh token。
- `/next`、`/app-assets`、`/auth`、`/api/v1` 通过 Caddy 正式到 `:8010`；根路径重定向到 `/next/`，未知旧路径和 `office.qyunsgen.com` 兼容重定向到 Vue。
- Gradio `pdf2zh.service` 在完整验收后已 `disable --now`；不删除 Python 包、配置、补丁、受保护下载、历史产物或归档 watcher，保留可逆恢复能力。
- Caddy 变更属于 `/home/dev/qyunsgen` 的独立生产配置变更，必须单独备份、审查、提交或记录部署工件。

## UI 参考吸收与边界（2026-09-30 增补）

用户提供的参考集合对本项目有帮助，但只吸收可验证的交互原则，不直接把 React 组件库移植到 Vue：

| 参考 | 可吸收的精华 | Qyunslation 的受控用法 | 明确不采用 |
|---|---|---|---|
| [Beautiful UI](https://www.beautifului.dev/) | AI 工作流的阶段、思考/处理状态、审批卡、差异表和任务行 | 用于预检、TranslationRun 阶段条、QA blocker/warning 和审计摘要；状态必须同时有文字、图标和颜色 | 不展示模型思维链、不把内部提示词或原始模型输出暴露给用户 |
| [beUI](https://beui.dev/) | 轻量可组合组件、抽屉/OTP/选择器的细微反馈、可定制 motion | 只提取 120–200ms 的短反馈和抽屉焦点管理模式；实现仍由 Vue 基础组件维护 | 不引入 React、Framer Motion 或 beUI Pro 运行时 |
| [Rare UI](https://rareui.com/) | “一个组件一个职责”、可复制源码、少量有辨识度的动效 | 仅用于空态、完成态和非阻断装饰；动效不得承载任务状态或阻断提示 | 不使用高对比 3D/粒子/磁吸效果，不引入其注册表、付费组件或额外归属要求 |
| [Transitions.dev](https://transitions.dev/) | 过渡应表达状态连续性，且可被 reduced-motion 关闭 | 仅为路由、抽屉、阶段条和对象检查器定义 token 化过渡；失败/阻断使用即时反馈 | 不使用持续循环、模糊遮罩或会降低文档可读性的动画 |
| [shadcn/ui](https://ui.shadcn.com/docs) | 源码可控、组合式基础组件、设计令牌和可访问状态 | 作为组件 API、键盘行为、表单/表格/抽屉验收的参考；继续使用 Vue 自有实现 | 不把 shadcn React 包作为生产依赖，不以“组件装上了”替代临床语义验收 |

### UI 质量增量门禁

067h 最终验收新增以下可执行门禁：

1. 登录、上传预检、任务阶段、对象检查器、QA 决策和词库筛选均使用同一套 Qyunslation tokens；业务 CSS 不得散落硬编码颜色。
2. 每个关键状态都有“状态名 + 图标 + 颜色/纹理”三重表达；禁止仅凭颜色或仅凭动效表达 blocker、warning、成功或降级。
3. 动效预算为 120–200ms；`prefers-reduced-motion: reduce` 下保留状态变化、焦点和错误信息，仅移除位移/缩放/循环动画。
4. 抽屉、对话框、筛选器和对象检查器完成键盘焦点进入、Escape 关闭、返回原焦点、背景滚动锁定和读屏名称验收。
5. 视觉快照使用真实中文药学内容（长术语、剂量、单位、表格和 QA 文案），不得以英文占位文本证明布局通过。
6. UI 参考站点只作为设计输入；依赖、许可证、归属和供应链检查不通过时，不得复制其源码或注册表。

## 子计划与依赖

| 子计划 | 内容 | 依赖 | 当前状态 |
|---|---|---|---|
| 067a | 运行时基线、设计输入与切换契约 | 无 | **已完成** |
| 067b | Authentik 应用、DNS、回调契约 | 067a | **已完成 · provider、Caddy、公共 DNS/JWKS 门禁通过** |
| 067c | 密钥注入与 sidecar 会话配置 | 067b | **已完成 · 生产 apply、0600 备份、sidecar 重启和健康验证通过** |
| 067d | 登录、回调、`/api/v1/me`、登出、CSRF 验收 | 067c | **已完成 · 真实公网 OIDC/API、CSRF、登出撤销通过** |
| 067e | Caddy 灰度路由 | 067d | **已完成 · Vue 正式入口和旧域名兼容重定向已部署** |
| 067f | 试点组与运行观察 | 067e | **已完成 · 真实 PDF 任务、产物下载、服务稳定性通过** |
| 067g | Gradio 退役与冗余模块审计 | 067f | **已完成 · 依赖修复、冗余审计和退役判定完成** |
| 067h | 交付证据、回滚与最终验收 | 067a–067g | **已完成 · Vue 正式入口、Caddy 回滚和 Gradio 可逆退役通过** |

## 附件适用性

`qyunslation-ui-ux-plan.md` 是 UI/UX 参考提案，不是当前仓库的绑定实施指令。采纳其文档对照、渐进式高级设置、检查器、术语治理、响应式和可访问性原则；覆盖其用户名/密码登录、旧颜色令牌、32px 点击区域、Gradio CSS 优先和任意 `ui=v2` 查询参数建议。PLAN-066 的 SSO、视觉令牌、44px 触控目标、Manifest/revision/QA 审计模型和 Vue 迁移边界优先。

## 当前缺口与观察门槛

- 人工浏览器视觉快照受当前执行环境无 Chromium 限制，未伪造为通过；真实公网 API/TranslationRun、构建和服务探针均已通过，后续只补视觉快照，不改变生产契约。
- `office-archive-watch.service` 曾因受保护虚拟环境缺少 `minio` crash-loop；已补齐锁定依赖并恢复 active，仍不得视为冗余模块。
- 根入口切换、旧域名兼容重定向、PDF/Office 归档 watcher 和 Caddy 回滚验证均已完成；服务停用与数据删除分离，UI 质量增量门禁已纳入 067h，不以静态截图冒充真实任务闭环。

## 完成与回滚原则

- 每个子计划先做专项验证，再精确提交、推送并记录 WT 证据。
- 任何认证、租户隔离、Gradio 根入口、旧下载或任务完整性回归，停止后续切换并恢复最近一次 Caddy 配置备份。
- 不回滚数据库迁移、不删除任务数据、不重复执行运行中的翻译任务。
