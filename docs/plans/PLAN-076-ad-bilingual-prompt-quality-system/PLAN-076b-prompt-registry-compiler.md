# PLAN-076b：提示词注册表、组合编译与快照

> 状态：**待实施**
> 父计划：[PLAN-076](./README.md)
> 依赖：[076a](./PLAN-076a-evaluation-contract-corpus.md) 的方向、文档类型和版本记录契约

## 目标

建立单一、可测试、不可静默漂移的提示词 SSOT。提示词按模块组合生成，并为 PDF、Office、术语抽取、QA 和修复提供同一版本/摘要语义。

## 模块接口

新增 `qyunslation/prompts/`：

```python
@dataclass(frozen=True)
class PromptContext:
    domain_profile: Literal["general", "ad"]
    direction: Literal["en-zh", "zh-en"]
    document_profile: Literal["医学研究文献", "临床研究文档"]
    task: Literal["translate", "extract", "qa", "repair"]

@dataclass(frozen=True)
class CompiledPrompt:
    profile_id: str
    version: str
    compiler_version: str
    system_prompt: str
    digest: str
    modules: tuple[str, ...]
```

注册表使用 JSON 或 Python 常量，不增加 YAML/Jinja 依赖；模板使用受限 `string.Template`，只允许注册变量，不接受源文或用户自由文本写入 system prompt。

## 任务

### Task 1：建立模块目录与注册表 schema

模块顺序固定为：`base → domain/ad → direction → document → task`。profile ID 固定为：

```text
ad.en-zh.literature.translate.v1
ad.en-zh.clinical.translate.v1
ad.zh-en.literature.translate.v1
ad.zh-en.clinical.translate.v1
```

extract/qa/repair 采用相同命名规则。注册表记录 active version、模块路径、适用方向/文档类型和 expected digest。

**验收标准：**

- [ ] 同一上下文编译结果字节稳定、摘要稳定。
- [ ] 未注册组合、未知变量、重复模块或摘要不一致 fail closed。
- [ ] `general` 继续走现有提示词，不被 AD 注册表接管。

**验证：**

```bash
uv run pytest tests/prompts/test_plan076_registry.py -q
```

**依赖：** 076a 契约
**预计规模：** M（registry、types、tests、基础模板，4–5 文件）

### Task 2：实现编译器与合同检查

编译器必须检查：角色存在、禁止增删原则存在、目标语言规则存在、输出规则存在；translate prompt 不得包含 QA JSON 指令，QA/repair prompt 不得包含用户自定义指令。

**验收标准：**

- [ ] 编译器不读取网络、数据库或环境中的自由提示词。
- [ ] 模板缺项时报稳定的 `PromptCompilationError(code, module)`。
- [ ] 日志只记录 profile/version/digest，不记录完整敏感 prompt。

**验证：**

```bash
uv run pytest tests/prompts/test_plan076_compiler.py -q
```

**依赖：** Task 1
**预计规模：** S（编译器和测试，2–3 文件）

### Task 3：实现 PromptSnapshot

快照写入 TranslationRun 的 `settings_snapshot.prompt_snapshot`，不新增数据库列；读取旧任务时该字段可为空。完整编译 prompt 写入运行目录 `prompt/compiled-system.txt`，权限与 runner config 一致为 0600，同时写 `prompt/manifest.json`。

**验收标准：**

- [ ] 重试沿用任务 generation 对应的 prompt snapshot，不随 active version 漂移。
- [ ] snapshot digest 与运行目录 prompt 不一致时阻断启动。
- [ ] 旧任务无 snapshot 时仍可读取和下载，不做自动回填。

**验证：**

```bash
uv run pytest tests/pipeline/test_plan076_prompt_snapshot.py -q
```

**依赖：** Task 2
**预计规模：** M（snapshot、run integration、tests，3–5 文件）

## Checkpoint 076b

- [ ] 4 个 translate profile 与 12 个 task profile 均能稳定编译。
- [ ] 版本切换不改变历史任务。
- [ ] 普通 API/日志不泄漏完整系统提示词。

## 不做

- 不做提示词在线编辑器。
- 不把术语表正文写进固定模板。
- 不在本阶段调用翻译模型。
