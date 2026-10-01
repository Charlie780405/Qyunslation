# PLAN-071g：参数设置、资料等级与模型治理

> 状态：**待实施**
> 父计划：[PLAN-071](./README.md)
> 依赖：[071b](./PLAN-071b-document-pipeline-manifest.md)、[071e](./PLAN-071e-qa-term-gate-formal.md)

## 目标

修复设置导航与管理员门禁；建立资料等级与模型配置白名单；DeepSeek 密钥仅存服务端；探测版本化，禁止静默跟别名升级与运行中切供应商。

## 现状

- `SettingsPage.vue`：点击只改 `activeSection`；三区始终渲染；无 URL sync；偏好 debounce 存 `/preferences` 但不应用 CSS。
- `/settings/admin`：`props.admin=true`，无路由角色守卫；侧栏不链到该路径。
- 能力：`session.hasCapability`；守卫只查 `workbench_v2`。
- 模型：`.env` `DOCUTRANSLATE_MODEL_ID=qwen3.6:35b-a3b`；`gateway/profiles.yaml`；`config.py` 双前缀；无 DeepSeek 生产配置。
- `pdf2zh_next` 支持 DeepSeek 服务参数（上游文档），但密钥/选型须由本服务治理。
- Next 预检 UI 无模型选择、无资料等级字段。

## 任务

### Task 1：设置分区与偏好生效

- `SettingsPage.vue`：每次只渲染当前 section；`?section=` 与 router 同步；前进后退可恢复。
- 「阅读与交互」立即应用：字体缩放、减少动效、布局密度、预览偏好 → `document.documentElement` class / CSS 变量。
- 「系统策略」仅 `system_admin`（`can_manage_policy`）可见；路由 meta + `beforeEach`；API 同步鉴权。

**验收：** vitest 覆盖 section 切换与 URL；无 capability 访问 `/settings/admin` 被拒；勾选 reduceMotion 后 DOM 有对应 class。

### Task 2：settings schema / effective

- `GET /api/v1/settings/schema`
- `GET /api/v1/settings/effective`：显示值、来源（system|user|default）、锁定状态与原因
- `GET/PUT /api/v1/admin/policies`：系统策略覆盖个人偏好，个人覆盖产品默认
- 现有 `/preferences` 可保留为用户层写入口，或委托到 effective 体系（二选一只留清晰文档）

**验收：** 锁定字段 PUT 被拒并返回原因。

### Task 3：模型配置白名单与资料等级

新增 `qyunslation/pipeline/model_profiles.py` + 表 `model_profile_version`（迁移 `071g0001`）：

| profile_id | 角色 | 模型 |
| --- | --- | --- |
| `internal-qwen-quality` | translator | 内网 `qwen3.6:35b-a3b` |
| `public-deepseek-flash` | translator | DeepSeek `deepseek-flash`（钉死探测版本） |
| `term-deepseek-flash` | term_suggester | 仅脱敏术语片段 |

兼容矩阵：

| classification | 允许 |
| --- | --- |
| confidential | 仅 `internal-qwen-quality`；禁止任何外部调用 |
| internal | 全文仅 Qwen；术语可选 `term-deepseek-flash` |
| public | Qwen 或 `public-deepseek-flash` |

- `GET /api/v1/model-profiles?classification=`
- `PATCH /api/v1/preflights/{id}`：classification、语言方向、model_profile_id、术语模型、任务参数
- `POST /translation-runs`：body 含 `document_classification`、`model_profile_id`；**服务端重验**兼容性
- 翻译前 UI 展示：资料等级、语言方向、文档类型、模型配置、是否允许外部处理、术语推荐模型
- DeepSeek Key：`QYUNSLATION_DEEPSEEK_API_KEY`（或等价密钥存储）；UI 只显示「已配置/未配置」
- 启动前探测：不可用则阻断创建；运行中禁止静默切换供应商
- 探测到行为/版本变化 → 新建 `model_profile_version` 行；旧任务继续引用旧快照
- CLI 凭据只走 config/env，不进 argv（保持 runner 196–198 纪律）

**验收：** 内部文件 API 指定 DeepSeek 全文 → 400/403；confidential 触发外部 → 阻断；试验配置未过金标门槛时标记 `experimental`。

### Task 4：任务快照字段

`settings_snapshot` / 专用列记录：profile_id、provider、model id、reported version、prompt version、termbase version、classification、egress scope、patch fingerprint（071a）。

**验收：** 创建 run 后快照只读；重试新 generation 可换配置但不改写旧快照。

## 数据库 / 接口变更

- 迁移 `071g0001`：`model_profile_version`；preflight/run 上 classification 与 profile 字段（或 metadata_json 规范化——优先正式列）
- 接口：preflight PATCH、model-profiles、settings schema/effective、admin policies

## 测试文件

- `tests/api/test_plan071g_model_classification_gate.py`
- `tests/api/test_plan071g_admin_policies.py`
- `tests/pipeline/test_model_profile_probe.py`
- `frontend` vitest：Settings section URL、admin guard、preference DOM class
- `tests/ui/test_plan071g_settings_source.py`

## 完成门槛

- 普通用户无法通过前端或直接 API 为内部文件指定外部全文模型。
- 设置分区刷新可恢复；系统策略 API+路由双门禁。
- deepseek-flash 不自动滚动升级。

## 验证命令

```bash
pytest -q tests/api/test_plan071g_*.py tests/pipeline/test_model_profile_probe.py tests/ui/test_plan071g_settings_source.py
cd frontend && npm test
```

## 不做

- 不开放任意模型 ID / 自定义 base URL。
- 不在日志中打印 API Key。
- 不把 DeepSeek 标为默认生产全文引擎，直至金标盲测通过（071i）。
