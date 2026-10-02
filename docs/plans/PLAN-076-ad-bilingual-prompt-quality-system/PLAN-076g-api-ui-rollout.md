# PLAN-076g：API/UI 可见性、审计与灰度

> 状态：**待实施**
> 父计划：[PLAN-076](./README.md)
> 依赖：[076b](./PLAN-076b-prompt-registry-compiler.md)–[076f](./PLAN-076f-semantic-qa-repair.md)

## 目标

让用户明确知道任务是否使用 AD 专业模式、哪个方向/文档 profile、哪版 prompt/termbase 以及为何被 QA 阻断；同时保持旧 API 和通用模式兼容。

## 任务

### Task 1：扩展预检与任务创建契约

在现有 body 中添加可选 `domain_profile`，不新增平行创建接口。服务端在 API 边界验证领域、方向、文档类型、模型等级和 AD 锚点；前端过滤不能代替后端校验。

**验收标准：**

- [ ] 老客户端不传字段时仍为 `general`，响应结构只新增可选字段。
- [ ] AD + 非中英方向/不支持 profile 返回 422 和稳定错误码。
- [ ] 同一 idempotency key 不能因 domain_profile 不同复用旧任务。

**验证：**

```bash
uv run pytest tests/api/test_plan076_run_contract.py -q
```

**依赖：** 076b、076d
**预计规模：** M（schemas、run creation、tests，3–5 文件）

### Task 2：扩展只读快照与 QA evidence

TranslationRun 响应增加 `prompt_snapshot`；QA items 在现有 `evidence` 中增加版本和 span 字段。完整 prompt 仅允许系统管理员通过服务器证据文件审计，不增加普通用户下载端点。

**验收标准：**

- [ ] source/target span 均经过服务端转义，前端按文本渲染。
- [ ] 缺少 snapshot 的历史任务正常显示“历史任务/无提示词快照”。
- [ ] 任务详情、下载门禁和审核记录引用同一 generation 的快照。

**验证：**

```bash
uv run pytest tests/api/test_plan076_prompt_qa_payload.py -q
```

**依赖：** 076b、076e–076f
**预计规模：** M（serializers、QA payload、tests，3–5 文件）

### Task 3：工作台 AD 模式与状态呈现

新增领域选择 `AD 专业翻译 / 通用医药翻译`；AD 下只显示两个方向和两个文档类型。任务详情展示 prompt version、termbase version、自动 QA、修复次数和 `内部测试版` 标识。

**验收标准：**

- [ ] UI 不提供生产提示词自由编辑框。
- [ ] `qa_degraded`、`qa_blocked`、`review_ready` 文案和操作权限清晰不同。
- [ ] QA evidence 支持键盘访问，源/译 span 不使用 `v-html`。

**验证：**

```bash
cd frontend && npm test && npm run type-check && npm run build
```

**依赖：** Tasks 1–2
**预计规模：** M（store/page/tests，3–5 文件）

### Task 4：灰度开关与回滚

新增：

```text
QYUNSLATION_AD_PROMPT_MODE=off|shadow|pilot|default
QYUNSLATION_AD_PROMPT_TENANTS=tenant-a,tenant-b
```

- `off`：拒绝新 AD 任务；历史任务可读。
- `shadow`：只做离线/评测回放，不改变用户产物。
- `pilot`：仅 allowlist 租户可创建 AD 任务。
- `default`：新工作台默认 AD，用户仍可显式选 general。

**验收标准：**

- [ ] mode 变化不改变在途/历史任务 snapshot。
- [ ] 回滚到 off 不删除事件、QA、术语或产物。
- [ ] 每次模式切换和 AD 任务创建写审计事件。

**验证：**

```bash
uv run pytest tests/api/test_plan076_rollout_modes.py -q
```

**依赖：** Tasks 1–3
**预计规模：** M（config、policy、audit tests，3–5 文件）

## Checkpoint 076g

- [ ] 旧 API 契约和 general 模式无回归。
- [ ] AD 选择、版本、QA 与修复证据在 UI 可见。
- [ ] 浏览器实测创建两个方向任务，刷新后状态与快照仍一致。
- [ ] off/pilot/default 切换可回滚且不破坏历史任务。

## 不做

- 不新增 `/prompt-profiles` 用户管理 API。
- 不允许 UI 上传或编辑生产提示词。
- 不为 PLAN-076 新建第二套任务详情页。
