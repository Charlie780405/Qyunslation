# WT-074：作者保护、单位审校、术语闭环与乱码门禁

> 状态：**工程闭环；legacy 真件 QA 待重跑**

## 执行摘要

PLAN-074 在 `/next` PDF 文献/Poster 路径上保护作者元数据、将研究单位纳入 QA 审校、结构化抽取专业术语并在正式批准前强制闭环，同时阻断乱码与 IL 标签残留。

## 变更明细

| 区域 | 交付 |
| --- | --- |
| 074a | `frontmatter.py` 作者/单位分类；BabelDOC 作者块跳过 LLM |
| 074b | affiliation 审校 API；`apply-corrections` 新一代；`translation_trace` 精确写回 |
| 074c | `term_extract` 结构化补充；Term/Affiliation 审校面板；`formal_gate` |
| 074d | `text_sanitize` 扩展；单/双语 PDF 阻断；`_QY_074_POSTPROCESS` 钩子 |

## 验证

```bash
bash scripts/verify-plan-074.sh
bash scripts/plan074-live-regression.py
```

- 后端/API/迁移/patch — PASS（58 tests）
- 前端 Vitest + axe + build — PASS
- Dupilumab 真件 — **BLOCKED**（legacy dual PDF 仍有 `IL_MARKUP_LEAK`/`TEXT_ENCODING_ARTIFACT`；术语金标 PASS）

## 生产发布（2026-10-02，PLAN-075a）

| 步骤 | 结果 |
| --- | --- |
| 备份 | `/home/dev/pdf2zh/backups/qyunslation-pre-074a-20261001T205548Z.dump` |
| Alembic | `073a0001` → **`074a0001`** |
| Git | `main` @ `6915de3`（074 六提交 + verify 脚本） |
| 部署 | sidecar 指纹 `7542777de0fd`；`affiliation-segments`/`apply-corrections` → **401** |
| 部署门禁 | PLAN-075b `deploy_gate.py` pre/post 检查 |

## 后续

用 PLAN-074 流水线重跑 Dupilumab Poster，使 live regression QA 段从 BLOCKED 转为 PASS。
