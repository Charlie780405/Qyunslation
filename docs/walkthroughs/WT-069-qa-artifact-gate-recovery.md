# WT-069：扫描 PDF QA/产物门禁恢复

## 事件与根因

- 生产任务：`FDA responses on PIND.pdf`，run `4ec45ef4-87a2-42e8-aa27-70c5ac48d3ec`。
- 失败状态：`failed / qa`，无 artifact，原因为 `pdf2zh_next completed without output artifacts`。
- runner 日志确认该 PDF 20 页中有 16 页被识别为扫描页；CLI 随后报告 `Scanned PDF detected`，并以空输出目录结束。
- 仅增加 `--auto-enable-ocr-workaround` 仍会对无文字层 PDF 报 `document contains no paragraphs`；根因是该文件没有可供 BabelDOC 解析的文字层。

## 修复

- 提交：`d3b3e5a`。
- PDF runner 在 CLI 无产物且源 PDF 被 HPD 判定为无文字层时，自动调用现有 `hpd_ocr` 生成 `input.hpd-ocr.pdf`，再以 `--skip-scanned-detection`、`--ocr-workaround` 和 `--disable-rich-text-translate` 重跑 CLI。
- OCR 失败、取消和重跑启动失败均保留明确原因；不把空目录伪装成成功。
- CLI 子进程环境显式加入 `/home/dev` 和仓库根目录，修复 OCR 文字层重跑时 `No module named 'qyunslation'` 的渲染错误。
- 普通文字 PDF 不进入 HPD OCR；只有首次运行无产物且检测到需要 HPD 时才触发兜底。

## 验证

- 回归测试：扫描 PDF“首次空产物 → HPD OCR → 重跑成功”、CLI 环境、取消和状态恢复均覆盖。
- `tests/workbench`、`tests/persist`、`tests/ui`：`175 passed`，8 个既有 Alembic deprecation warnings。
- 真实 FDA PDF 两页范围探针：HPD 生成 72 MB searchable PDF，重跑生成双语和单语 PDF，runner 状态 `succeeded / export / 100%`。
- 生产 sidecar 已重启并 active；本机 health：`{"schema":"034h","db":"ok"}`。
- 公网 `/next/workbench`：200；`/api/v1/health`：200；未认证 `/api/v1/me`：401；`pdf2zh_next`：2.9.0。

## 操作说明

生产中原来的失败任务不会被静默改写。点击该任务的“重试”会创建新的 generation，并自动使用新的扫描件 OCR 兜底；成功后才会进入正式 artifact 下载列表。
