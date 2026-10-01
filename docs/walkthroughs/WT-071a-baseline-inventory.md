# WT-071a：质量基线、旧能力盘点与验收样本

状态：**实施中（契约层已合入；真实 FDA 二进制本环境缺失 → 样本跑批 BLOCKED）**

父计划：[PLAN-071](../plans/PLAN-071-translation-quality-pipeline/README.md)
子计划：[PLAN-071a](../plans/PLAN-071-translation-quality-pipeline/PLAN-071a-baseline-inventory.md)

## 本轮交付

| 产物 | 路径 |
| --- | --- |
| FDA 基线清单 | `docs/gold/plan071/baseline/MANIFEST.md` |
| 旧能力盘点 | `docs/contracts/plan071-legacy-capability-inventory.md` |
| 验收矩阵 | `docs/contracts/plan071-acceptance-matrix.md` |
| 七类金标 catalog | `docs/gold/plan071/catalog.json` |
| expectation schema + 7 份期望 | `docs/gold/plan071/expectation.schema.json`、`expectations/*.json` |
| 补丁指纹脚本 | `scripts/plan071_patch_fingerprint.py` |
| 验证脚本 | `scripts/verify-plan-071a.sh` |
| 测试 | `tests/scripts/test_plan071_patch_fingerprint.py`、`tests/gold/test_plan071_expectations_schema.py` |

## 验证

```bash
bash scripts/verify-plan-071a.sh
```

期望：文档与 pytest PASS；若无 `C-fda-pind.pdf` 则 SUMMARY: BLOCKED（不失败退出）。

## 手机续做接手（下一刀）

1. **分支**：`cursor/plan-071-docs-b2dc`（或从该分支拉 `cursor/plan-071b-pipeline-b2dc`）。
2. **PR**：关注 PLAN-071 文档/071a PR；合并后开 071b。
3. **下一子计划**：[PLAN-071b](../plans/PLAN-071-translation-quality-pipeline/PLAN-071b-document-pipeline-manifest.md)
   - 建 `qyunslation/pipeline/`
   - `Pdf2zhRunner` 降级为执行器，禁止 CLI 成功即 `succeeded`
   - Manifest 2.0.0
4. **缺件**：把 sha256=`dae7401230ca270f1cedfa2052235dba5952d4f0a577e91dc84c36c0ba7b9cb4` 的 FDA PDF 放到 gold root，更新 `artifacts/plan071/baseline/`（gitignore）。
5. **不要做**：不要在未完成 071b 前改正式导出门禁语义；不要删 Gradio 补丁。

## 证据备注

- 本 Cloud 环境无 uv `pdf2zh-next` site-packages → 指纹 `present_count=0` 属预期，脚本仍写 JSON。
- 生产/Vultr 机上重跑指纹，把 `fingerprint_sha256` 贴回本 WT「现场指纹」节。

### 现场指纹

（待有 site-packages 的机器填写）

```text
fingerprint_sha256:
present_count:
gui_sha256:
```
