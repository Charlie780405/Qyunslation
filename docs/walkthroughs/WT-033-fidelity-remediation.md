# WT-033 学术 PDF 最终产物保真补救（033g–033l）

> 计划：[PLAN-033](../plans/PLAN-033-pdf-fidelity/PLAN-033-pdf-fidelity.md)
> 分支：`codex/plan-033g-fidelity-remediation`
> 日期：2026-09-09
> 结论：**已合并并部署到生产 WebUI；最终产物总验收仍只覆盖子集。** `origin/main` = `dc1bdd3`。`verify-plan-033l.sh` 对暂存 mono/dual 为 PASS，但检查器只覆盖 Figure/Table 计数、PENDING 文本和参考文献标题。

## 分支与提交

| 提交 | SHA |
| --- | --- |
| 提示词与 033g–033l 计划 | `29274bd` |
| 033g 执行契约与模型溯源 | `a677aeb` |
| 033h 参考文献与正文字重 | `046d321` |
| 033i 表格结构化 | `97d197f` |
| 033j 表格翻译与续页 | `ddcfcad` |
| 033k 图片排版与 QC | `9b1c805` |
| 033l 总门初稿 | `5a65132` |
| 033h 术语补丁锚点 | `690af8b` |
| 028 接受 PRESERVE | `3f7b3c4` |
| 033h 真正挂钩 `_should_translate` | `2f23d00` |
| 033h 挂钩 `process_page` 入队 | `a85f18f` |

工作区：`/home/dev/.codex/worktrees/033g/qyunslation`  
保护：未改动、未提交 `glossaries/auto-proper-nouns.csv`。

## 模型与端点

- 锁定并实际用于暂存重译：`qwen3.6:35b-a3b` @ `http://100.67.66.123:11434`（Ollama host；OpenAI 兼容形态为 `http://100.67.66.123:11434/v1`）
- 配置来自 `/tmp/plan033-staging/config.toml`（`gui=false` 副本），CLI 显式传入 `--ollama-model` / `--ollama-host`
- `model_trace` 代码路径已有；**本轮 CLI 重译没有写入任务 Manifest 的 model_trace**

## 门禁

| 门禁 | 结果 |
| --- | --- |
| verify-plan-033g.sh | PASS |
| verify-plan-033h.sh | PASS |
| verify-plan-033i.sh | PASS |
| verify-plan-033j.sh | PASS |
| verify-plan-033k.sh | PASS |
| verify-plan-033l.sh | **PASS**（暂存 PDF；断言子集） |
| verify-plan-033.sh | 本 WT 更新后另跑 |
| verify-plan-028.sh | **PASS**（修复列布局断言后） |
| verify-plan-029.sh | **PASS** |
| verify-plan-030e.sh | 先前串行被 `tail` 拖住，另跑中 |

样本：`/home/dev/.hermes/attachments/1-s2.0-S2666636725013958-main.pdf`  
SHA-256 `c88ea994746e13904ed012943130896426b8812f939ae14917e1c48f59b2f8dc`。扫描 Figure=2 / Table=4。

## 真实产物

暂存重译（033h `process_page` 挂钩生效后）：

- mono：`/tmp/plan033-staging/1-s2.0-S2666636725013958-main.no_watermark.zh.mono.pdf`
- dual：`/tmp/plan033-staging/1-s2.0-S2666636725013958-main.no_watermark.zh.dual.pdf`
- 第 10 页标题为 `REFERENCES`（不是「参考文献」），条目保持英文作者/期刊/DOI
- 当前 033l 检查器：`fail=[]`，`pass=figure_count=2, table_count=4, no_pending_text`

补丁现场：`scripts/check-babeldoc-fidelity-033l.py` 现为 4 个文件 `:1`。备份在 `/home/dev/pdf2zh/babeldoc-bak-plan033l-20260909T150000Z`。

## 部署 / 烟测 / 回滚

**已部署。** 2026-09-09T07:39Z 重启 `pdf2zh.service`。

- merge：`dc1bdd3`（`merge: PLAN-033 最终产物保真补救（033g–033l）`）
- `git push origin main`：`9e2b78f..dc1bdd3`
- 生产 `PYTHONPATH=/home/dev/qyunslation` 已 fast-forward 到 `dc1bdd3`（`glossaries/auto-proper-nouns.csv` 保持 dirty，未提交）
- 单元已写入 `ExecStartPre=apply-pdf2zh-fidelity-033h.py`，启动自检退出 0
- 补丁签名四文件 `:1`；备份 `/home/dev/pdf2zh/bak-plan033l-20260909T073909Z`
- 烟测：`http://127.0.0.1:7860/` → 200；`paragraph_is_preserved("REFERENCES")` 为 True

回滚 BabelDOC 源文件：

```bash
SITE=/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages
BAK=/home/dev/pdf2zh/babeldoc-bak-plan033l-20260909T150000Z
cp -a "$BAK/il_translator_llm_only.py" "$SITE/babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py"
cp -a "$BAK/automatic_term_extractor.py" "$SITE/babeldoc/format/pdf/document_il/midend/automatic_term_extractor.py"
cp -a "$BAK/il_creater.py" "$SITE/babeldoc/format/pdf/document_il/frontend/il_creater.py"
cp -a "$BAK/fontmap.py" "$SITE/babeldoc/format/pdf/document_il/utils/fontmap.py"
```

服务回滚：

```bash
cp /home/dev/pdf2zh/bak-plan033l-20260909T073909Z/pdf2zh.service /home/dev/.config/systemd/user/pdf2zh.service
SITE=/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages
BAK=/home/dev/pdf2zh/bak-plan033l-20260909T073909Z
cp -a "$BAK/il_translator_llm_only.py" "$SITE/babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py"
cp -a "$BAK/automatic_term_extractor.py" "$SITE/babeldoc/format/pdf/document_il/midend/automatic_term_extractor.py"
cp -a "$BAK/il_creater.py" "$SITE/babeldoc/format/pdf/document_il/frontend/il_creater.py"
cp -a "$BAK/fontmap.py" "$SITE/babeldoc/format/pdf/document_il/utils/fontmap.py"
cp -a "$BAK/gui.py" "$SITE/pdf2zh_next/gui.py"
systemctl --user daemon-reload
systemctl --user restart pdf2zh.service
```

## 尚未完成 / 无法证明

1. Table 1–4 表题/单元格/脚注的终态执行证据与矢量重排（033j 策略未接到 PDF 写出）。
2. Table 1 旋转整页表已翻译。
3. Figure 1 零截断/越框/漏译，以及 `FONT_BELOW_TARGET` / 450–600 DPI。
4. 粗体标题 vs 普通正文的渲染字重。
5. 任务级 `model_trace` 写入成功结果。
6. 续页与双语续页左侧原稿一致性（本样本未见续页）。
7. 修复后的完整 `verify-plan-030e.sh` / `verify-plan-033.sh` 未在本部署窗口重跑收口。
