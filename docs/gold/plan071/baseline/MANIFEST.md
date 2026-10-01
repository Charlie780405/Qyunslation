# PLAN-071 基线证据清单（FDA 扫描信）

> 状态：基线已登记（本环境无二进制副本时标记 `BINARY_ABSENT`）
> 对应子计划：[PLAN-071a](../../plans/PLAN-071-translation-quality-pipeline/PLAN-071a-baseline-inventory.md)
> 金标 catalog：`docs/gold/plan034/catalog.json` → `C-fda-pind`

## 源文件

| 字段 | 值 |
| --- | --- |
| catalog_id | `C-fda-pind` |
| title | FDA responses on PIND scanned regulatory correspondence |
| format | pdf（扫描件，约 20 页） |
| sha256 | `dae7401230ca270f1cedfa2052235dba5952d4f0a577e91dc84c36c0ba7b9cb4` |
| catalog_relpath | `C-fda-pind.pdf` |
| gold_root_env | `QYUNSLATION_PLAN034_GOLD_ROOT`（默认 `/home/dev/qyunslation-gold/plan034`） |
| runtime_session_path（易失） | `/home/dev/pdf2zh/pdf2zh_files/5fa54bcf-4843-4e97-8cd0-85c797fa9b5d/FDA responses on PIND.pdf` |
| test_helper | `tests/structure/sample_paths.py` → `pind_sample()` / `SCANNED_PAGE_COUNT=20` |
| ocr_variant | `C-fda-pind-ocr` sha256 `ecdffaeafce7d9dfb6846ef402a2c81e485874438c418110fa7e0dedb3706bdc` |

本 Cloud Agent 环境探测结果（2026-10-01）：

- runtime 会话 PDF：**缺失**
- gold root PDF：**缺失**
- 结论：`BINARY_ABSENT` — 实施机需用同 sha256 文件放入 gold root 或设置 env 后再跑真实样本。

## 当前缺陷索引（来自生产观察 / PLAN-071 根因）

| 缺陷 ID | 现象 | 预期 |
| --- | --- | --- |
| D-logo | FDA Logo 丢失或未回填 | `preserve_kind=logo`，源哈希一致 |
| D-th | 出现 `^{th}` 上标伪影 | 原子 span / letter_layout 清洗后无该串 |
| D-email | 邮箱断行或半角破坏 | 邮箱为原子 span，完整可点 |
| D-addr | 地址/签名区错行 | letter 角色重绘后阅读顺序正确 |
| D-gate | CLI 成功即 `succeeded/export/100%` | 须经 QA + review 才正式 |

本地大文件与 runner 日志放入（gitignore）`artifacts/plan071/baseline/`：

```text
artifacts/plan071/baseline/
  source.sha256          # 与上表一致
  runner.log             # 出错任务日志副本
  translation_run.json   # 台账字段快照
  bad-output.pdf         # 可选错误产物（不入库）
  screenshots/           # Logo/^{th}/邮箱等截图
  patch-fingerprint.json # scripts/plan071_patch_fingerprint.py 输出
```

## 台账字段基线（创建路径观察）

来源：`qyunslation/api/v1.py` 创建 TranslationRun 时：

| 字段 | 创建时典型值 | 问题 |
| --- | --- | --- |
| `status` | queued → … → succeeded | CLI 成功即 succeeded |
| `stage` | validation → export | 跳过真实 qa/review |
| `progress` | 100 | 伪装完成 |
| `manifest_version` | null/空 | 未赋值 |
| `qa_summary` | `{blocker:0,warning:0,info:0}` | 未跑检查 |
| `term_summary` | `{status: snapshot_pending}` | 未解析 |
| `formal_export` | true（产物） | 无水印审核稿 |

证据代码：`qyunslation/workbench/runner.py` 672–683；`api/v1.py` ~624–629、~881–882。

## 复现步骤（有二进制时）

1. 将 `C-fda-pind.pdf` 放入 gold root，校验 sha256。
2. 经 `/next` 上传并启动 TranslationRun（当前 PDF runner）。
3. 保存 `runner.log`、产物 mono/dual、DB 行 JSON 到 `artifacts/plan071/baseline/`。
4. 对照缺陷表截图。
5. 跑 `python scripts/plan071_patch_fingerprint.py -o artifacts/plan071/baseline/patch-fingerprint.json`。

## 接手提示（手机续做）

- 下一刀：**071b** DocumentPipeline + Manifest 2.0（分支可续 `cursor/plan-071-docs-b2dc` 或新开 `cursor/plan-071b-…-b2dc`）。
- 071a 完成门槛：本清单 + 盘点合同 + 指纹脚本测试 + 七类期望 + 验收矩阵。
- 缺二进制不阻塞 071a 文档/脚本合入；阻塞的是真实样本跑批（071i）。
