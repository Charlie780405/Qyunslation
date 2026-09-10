---
name: qyunslation 全面整治
overview: 对 qyunslation 做一次全量整治：彻底完成 docutranslate→qyunslation 重命名以恢复可重启能力，砍掉 11.5 秒的 docling 启动开销，按实测拐点校准并发参数，并修复安全漏洞与并发/资源缺陷。
todos:
  - id: phase0
    content: 阶段 0：建 docutranslate symlink 兜底，验证 import qyunslation.app 与服务可重启
    status: completed
  - id: 006a
    content: 阶段 006a：彻底重命名 421 条 import、pyproject、4 个 spec、Dockerfile、CI、vite 配置；config.py 加环境变量双读；清理旧 editable 安装与 symlink
    status: completed
  - id: 006b
    content: 阶段 006b：拆分 ConverterDoclingConfig 或延迟 import docling，处理 core/factory.py；用 -X importtime 出前后对比落 docs/perf/baseline-006b.json
    status: completed
  - id: 006c
    content: 阶段 006c：.env 写入 CONCURRENT=8、TIMEOUT=300；评估 CHUNK_SIZE 8000 并跑 JSON 完整性回归；新增 benchmark-plan-006c.py
    status: completed
  - id: 006d
    content: 阶段 006d：恢复 TLS 校验并加开关、可选 API token 鉴权、task_id 扩位、Zip Slip 校验、修 json/srt 模板 XSS、收紧 CORS、限制 MCP 文件与 URL、前端 key 改 sessionStorage、去硬编码内网默认值
    status: completed
  - id: 006e
    content: 阶段 006e：image_overlay 改 asyncio.to_thread、tasks_state TTL 清理、启用 _lock、cacher 加锁、修 custom_api finally 与裸 except、修 extensions import 路径
    status: completed
  - id: 006f
    content: 阶段 006f：新增 pytest CI job、删孤儿 translation_cache.json、归档 enhanced_translate.py、统一 glossary_db.json、补 test_app.py、写 scripts/verify-plan-006.sh
    status: completed
isProject: false
---

= qyunslation 运行状况审核与全面整治

## 审核结论摘要

四个方向的排查结论，均有实测证据支撑。

### 1. 安全性（开源来源审查）

未发现恶意后门。全库无 `eval`/`exec`/`pickle.loads` 业务调用，无遥测上报，`subprocess` 均为预期用途（LibreOffice、pandoc、indexer）。`uv.lock` 里的 `sentry-sdk` 只是 `fastapi-cloud-cli` 的传递依赖，代码从未 `import sentry_sdk`。`.env` 从未进入 git（`git ls-files .env` 为空）。

实际风险来自配置和经典 Web 漏洞，不是来源：

- TLS 校验被全局关闭：[qyunslation/agents/agent.py](qyunslation/agents/agent.py) 第 860 行 `verify=False`，[converter_mineru.py](qyunslation/converter/x2md/converter_mineru.py) 第 53-54 行同样。现在接内网 http ollama 无影响，但一旦切商业 API（DeepSeek），`Authorization: Bearer sk-...` 就可被中间人截获。
- 全部 `/service/*` 无鉴权，`task_id` 仅 8 位 hex（[app.py](qyunslation/app.py) 第 319 行）可枚举。当前只监听 `127.0.0.1:8010`，实际暴露有限，但 CLI 默认 CORS regex 是 `^(https?://.*|null|file://.*)$`，等于允许任意站点。
- Zip Slip：[extensions/image_replace.py](qyunslation/extensions/image_replace.py) 第 27-28 行 `z.extractall(tmp)` 未校验成员路径。
- 导出 HTML 存储型 XSS：[template/json.html](qyunslation/template/json.html) 第 57 行把原始 JSON 直插 `<script>`；[template/srt.html](qyunslation/template/srt.html) 第 13 行对字幕用 `| safe`。
- 前端把 API Key 落 localStorage：[PlatformSelector.vue](frontend/src/components/common/PlatformSelector.vue) 第 126-129 行。
- MCP 模式（Docker 默认 `--with-mcp`）可读任意本地文件与任意 URL：[mcp/server.py](qyunslation/mcp/server.py) 第 535-568 行，构成 SSRF + 本地文件读取。

### 2. 模型可用性（实测通过，建议继续用泰州本地模型）

`qwen3.6:35b-a3b` 在 `http://100.67.66.123:11434` 常驻显存 23.5 GB，context 65536，capabilities 含 thinking/tools/vision。用项目真实 segments prompt 实测 20 段医学文本（1903 字节）：

- 关闭思考（项目当前 `THINKING=disable`）：3.2 秒，153 tok/s，JSON ID 完整性 OK，EASI-75/TEAEs/IGA 0/1/Q2W 术语全部正确保留
- 开启思考：20.7 秒，4711 completion token 中约 97% 是思考过程，译文仅微幅改善

结论是本地模型足够胜任，且数据不出内网、无调用成本，优于换 DeepSeek。DeepSeek 只建议作为兜底：本项目的 segments 流程要求严格 JSON，失败会触发 `unresolved_errors` 门禁阻止导出（[server/core.py](qyunslation/server/core.py) 第 119-124、580-583 行），配一个商业 API 作降级目标可提升可用性。注意当前 `.env` 里 `API_KEY=ollama`，没有任何商业 key。

并发配置是错的。实测吞吐拐点（20 段/请求）：

- 并发 1：2.5s，142 tok/s
- 并发 4：6.8s，204 tok/s，中位延迟 5.2s
- 并发 8：12.2s，217 tok/s，中位延迟 7.9s
- 并发 16：24.3s，224 tok/s，中位延迟 13.9s
- 并发 30（当前默认）：44.3s，228 tok/s，中位延迟 24.1s

ollama 实际并行度约 4。超过 8 之后聚合吞吐只涨 5%，单请求延迟涨 3 倍，多出的请求纯排队并放大 timeout 风险。

### 3. 启动过慢（已定量归因）

瓶颈不在 lifespan（只建 httpx client 和任务字典），而在 `import app` 阶段：

- `ConverterDoclingConfig` 只是个 4 字段 dataclass（[converter_docling.py](qyunslation/converter/x2md/converter_docling.py) 第 28-34 行），却和 `ConverterDocling` 同文件，该文件顶层 import 整个 docling 栈（第 11-16 行）
- [server/core.py](qyunslation/server/core.py) 第 73-74 行只为拿这个 dataclass 就无条件触发上述 import
- 实测 `import docling.document_converter` 单独耗时 **11.5 秒**（含 torch 3.1 秒）
- 你的 `.env` 配的是 `CONVERT_ENGINE=identity`，压根不走 docling 路径

docling / torch / cv2 / onnxruntime / rapidocr 在 `.venv` 里全部已安装（dev 依赖组）。其余库合计约 2 秒，FastAPI+uvicorn 约 0.8 秒。总启动约 15 秒，其中 11.5 秒是纯浪费。

`core/factory.py` 第 11 行是同样的无条件 docling import，虽只在 SDK 路径。

### 4. 隐藏缺陷（最严重的一项是定时炸弹）

**服务现在无法重启。** 进程 3098717 从 8 月 23 日跑到现在（监听 127.0.0.1:8010，`/service/meta` 返回 1.7.8），但它依赖的 `docutranslate` 导入名已经断了：

- `__editable__.docutranslate-1.7.8` 的 finder 指向 `/home/dev/docutranslate/docutranslate`，该目录不存在
- [scripts/deploy-plan-005.sh](scripts/deploy-plan-005.sh) 第 21 行 `ln -sfn qyunslation "$ROOT/docutranslate"` 创建的符号链接已消失，且从不在 git 里
- 实测 `from docutranslate.app import app` 立即抛 `ModuleNotFoundError`
- 全库 421 条 `import docutranslate` 语句、99 个 .py 文件全部依赖它

连带影响：13 个测试文件、4 个 PyInstaller spec、`.github/workflows/build-macos.yml` 第 53 行、`pyproject.toml` 的 `name`/`include`/`scripts`/`version attr` 全部指向 `docutranslate`。标准 `pip install -e .` 按 `include = ["docutranslate*"]` 找不到 `qyunslation/`。

其余缺陷：

- extensions import 路径断裂：[custom_api.py](qyunslation/custom_api.py) 第 17-18 行按根目录平铺 import `glossary_db` / `image_translate`，实际文件在 `qyunslation/extensions/`。被 [app.py](qyunslation/app.py) 第 1179-1184 行 try/except 静默吞掉，术语表与图片嵌字 API 一直不可用而无人知。
- 事件循环阻塞：[image_overlay_workflow.py](qyunslation/workflow/image_overlay_workflow.py) 第 33-34 行 `async def translate_async` 直接同步调 `translate()`，内部用 `urllib.request.urlopen`，单个图片任务会卡死整个服务。
- 任务状态无界增长：`tasks_state` / `tasks_log_histories` 仅在客户端调 `/service/release/{task_id}` 时释放；成功任务的 `temp_dir` 也不删（[server/core.py](qyunslation/server/core.py) 第 731-739 行只在 `error_flag` 时 rmtree）。当前进程 RSS 已 407 MB。
- `asyncio.Lock` 定义了但全文件从未使用（第 265-266 行）；`md_based_convert_cacher` 全局 `OrderedDict` 被 `asyncio.to_thread` 并发访问且无锁。
- `translation_cache.json`（50 KB，根目录）是孤儿文件，全库无任何读写代码，其 key 是纯 chunk hash 不含 model_id/to_lang，将来若被重新接入会命中错模型的缓存。
- [enhanced_translate.py](enhanced_translate.py) 是阶段 4 早期整合脚本，功能已被 `custom_api` 和 `ImageOverlayWorkflow` 覆盖，且 import 已断裂。
- `.github/workflows/` 只有 3 个 PyInstaller 构建，没有 pytest job；`pyproject.toml` 第 71 行 `--cov=docutranslate` 包名也是错的。
- 硬编码内网拓扑：[extensions/image_translate.py](qyunslation/extensions/image_translate.py) 第 21-28 行默认值写死 `100.67.66.123` 与 `/home/dev/pdf2zh/glossaries/qx027n.csv`。

工作区卫生本身没问题，`.gitignore` 覆盖了 `.coverage`/`htmlcov`/`__pycache__`/`.env`/日志/缓存，无误提交，`git status` 干净。

---

## 整治方案

按项目既有惯例落 `docs/plans/PLAN-006-audit-remediation/` 加 `scripts/verify-plan-006.sh`，分 6 个子阶段。

### 阶段 0：先恢复可重启（5 分钟，先做）

重命名是大动作，期间必须保证服务随时能起。先建符号链接兜底并验证：

```bash
ln -sfn qyunslation /home/dev/qyunslation/docutranslate
.venv/bin/python -c "from docutranslate.app import app; print('ok')"
```

确认能起来之后再进阶段 1。阶段 1 完成后这个链接和 `docutranslate-1.7.8` 的 editable 安装一并删除。

### 阶段 006a：彻底重命名（P0）

- 批量替换 99 个 .py 文件里的 421 条 import：`from docutranslate` → `from qyunslation`，`import docutranslate` → `import qyunslation`
- 非 import 的字符串引用：`server/core.py` 第 586 行临时目录前缀 `docutranslate_{task_id}_`、`sdk.py`、`mcp/server.py`
- `pyproject.toml`：`name`、`packages.find include`、`package-data`、`project.scripts`、`dynamic version attr`、pytest `--cov=qyunslation` 与 `env` 段
- 4 个 spec 文件（`lite.spec` / `full.spec` / `lite_mac.spec` / `lite_mac_x86_64.spec`）的 `import docutranslate`、`datas` 路径、`Analysis(['docutranslate/app.py'])`
- `Dockerfile` 的 `COPY docutranslate ./docutranslate` 与 ENTRYPOINT 命令名
- `.github/workflows/build-macos.yml` 第 53 行、`frontend/vite.config.js` 的 `outDir: ../docutranslate/static`
- 环境变量前缀**保留** `DOCUTRANSLATE_`，只在 [config.py](qyunslation/config.py) 加双读（`QYUNSLATION_*` 优先、回落 `DOCUTRANSLATE_*`）。理由是 `.env`、`Dockerfile`、`scripts/office.env.example`、systemd 单元、docs 都依赖它，同时改会把配置风险和代码风险叠在一起。
- 清掉旧安装：卸载 `docutranslate-1.7.8` editable，删 `docutranslate` symlink，`uv sync` 重装，确认 site-packages 只剩 `qyunslation`
- `scripts/deploy-plan-005.sh` 第 20-21 行的 symlink 逻辑删除

验收：`uv run qyunslation --help` 通过；`rg -c "docutranslate" -g '*.py' --glob '!.venv'` 归零（README/更新日志的历史记述可留）。

### 阶段 006b：启动加速（15 秒 → 约 3 秒）

- 把 `ConverterDoclingConfig` 拆到不 import docling 的独立模块（例如 `converter/x2md/converter_docling_config.py`），或改为 `server/core.py` 第 824-825 行分支内延迟 import。后者改动更小。
- 同样处理 `core/factory.py` 第 11 行
- `conditional_import("docling")` 保留（只 0.04 秒，`DOCLING_EXIST` 判断仍需要）
- 修复 `custom_api.py` 的 import 后，cv2 会进入启动链（0.44 秒，可接受）；`extensions/image_translate.py` 的 cv2/numpy/PIL 可下沉到函数内
- 用 `python -X importtime` 出前后对比数据，落 `docs/perf/baseline-006b.json`

### 阶段 006c：模型与并发校准

- `.env` 显式写入 `DOCUTRANSLATE_CONCURRENT=8`（实测拐点，取 93% 峰值吞吐而延迟只有并发 30 的三分之一）
- `DOCUTRANSLATE_TIMEOUT` 从 1200 降到 300：并发 8 时单请求中位 7.9 秒，1200 秒的超时意味着真故障要等 20 分钟才暴露
- `THINKING=disable` 保持不变（实测支撑）
- 评估 `CHUNK_SIZE` 从 4000 提到 8000：context 有 65536，chunk 翻倍可把请求数减半。需先跑 JSON ID 完整性回归确认不引入错位，不通过就维持 4000。
- 可选：把 DeepSeek 配成失败降级目标，用于本地模型 JSON 失败触发导出门禁时兜底
- 校准脚本沿用 `scripts/benchmark-ollama-003b.py` 模式，新增 `scripts/benchmark-plan-006c.py`

### 阶段 006d：安全加固

- `verify=False` → 默认 `True`，新增 `DOCUTRANSLATE_TLS_VERIFY` 开关供内网自签场景显式关闭（`agents/agent.py` 第 860 行、`converter_mineru.py` 第 53-54 行）
- 新增可选 `QYUNSLATION_API_TOKEN`：设置时对 `/service/*` 强制 Bearer 校验，未设置时保持现有行为，避免打断本地前端和 `scripts/` 里的调用方
- `task_id` 从 `uuid4().hex[:8]` 改为 `[:16]`（`app.py` 第 319 行）
- `image_replace.py` 第 27 行 `extractall` 前校验每个成员路径落在目标目录内
- `template/json.html` 改用 `{{ jsonData | tojson }}`；`template/srt.html` 去掉 `| safe`，改由 exporter 侧做转义后再替换换行
- CLI 默认 `--cors-regex` 收紧为 localhost 白名单（`cli.py` 第 52-55 行）
- MCP 的 `file_path` 增加白名单目录与 URL scheme/host 限制（`mcp/server.py` 第 535-568 行）；Docker ENTRYPOINT 的 `--with-mcp` 改为按需
- 前端 API Key 改 sessionStorage 或内存态（`PlatformSelector.vue` 第 126-129 行）
- `extensions/image_translate.py` 第 21-28 行去掉硬编码内网默认值，改为必需环境变量并在缺失时明确报错
- 确认 `.env` 权限 600

### 阶段 006e：并发缺陷与资源治理

- `image_overlay_workflow.py` 第 33-34 行改 `return await asyncio.to_thread(self.translate)`
- `tasks_state` 加 TTL 后台清理（完成 N 小时后自动 release 并 rmtree `temp_dir`），成功任务的 `temp_dir` 纳入清理
- 启用已定义未使用的 `self._lock` 保护 `tasks_state` 读写路径
- `cacher/md_based_convert_cacher.py` 加 `threading.Lock`
- `custom_api.py` 第 29-40 行 `tmp_in`/`tmp_out` 预初始化为 `None`，消除 finally 的 UnboundLocalError
- `exporter/md/md2html_exporter.py` 第 45 行裸 `except:` 改 `except Exception` 并记日志
- 修 extensions import 路径：`custom_api.py`、`image_replace.py`、`enhanced_translate.py` 及相关 tests 改为 `qyunslation.extensions.*`；去掉 `custom_api.py` 第 15 行的 `sys.path.insert`
- `app.py` 第 1179-1184 行的 try/except 保留但把 warning 升级为显式启动横幅，避免再次静默失效

### 阶段 006f：CI、测试与卫生

- `.github/workflows/` 新增 pytest job（现有 3 个 workflow 全是 PyInstaller 构建）
- 4 个 spec 文件路径更新（已在 006a 覆盖），产物名 `DocuTranslate-*` 按需改
- 删除孤儿 `translation_cache.json`
- `enhanced_translate.py` 移入 `archive/` 或删除
- 统一 `glossary_db.json` 位置（根目录那份 49 字节与 `extensions/glossary_db.json` 两个路径易混淆），以 `DB_PATH` 为准
- 补 `tests/test_app.py` 端到端 API 用例
- `scripts/verify-plan-006.sh` 覆盖：无 symlink 下 `import qyunslation.app` 成功、启动耗时低于阈值、`.env` 并发参数生效、`rg docutranslate` 归零、pytest 全绿

---

## 需要注意

- 阶段 006a 完成后必须重启 8010 服务，会有短暂中断。当前进程一旦停止就无法用旧代码起回来（`docutranslate` 已断），所以重启前务必先在另一个 shell 里验证 `import qyunslation.app` 成功。
- 阶段 006c 的 `CHUNK_SIZE` 调整属于可回退实验，不通过就维持 4000，不要为省请求数牺牲 JSON 完整性——失败会直接触发导出门禁。
- 006d 的 API 鉴权做成默认关闭，避免打断 `scripts/office-archive-watch.py` 等现有调用方。