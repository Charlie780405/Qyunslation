# WT-050g：UI/UX 交付验收

对应 [PLAN-050g](../plans/PLAN-050-qyunslation-ui-ux/PLAN-050g-verify-delivery.md)

## 门禁

```bash
bash scripts/verify-plan-050.sh
```

默认：静态文档 + pytest + 施工面/补丁签名 + 登录后 DOM 含 `qy-050-appbar`。

完整金标翻译矩阵（PDF/DOCX/图/失败样本逐条跑通）默认不强制；设 `QYUNSLATION_PLAN050_LIVE=1` 才探上传。缺样本标 **BLOCKED**，不算工程 FAIL。

## 补丁与回滚

- 序 31：`apply-pdf2zh-050-workbench.py`（幂等，标记 `_qy_050_*`）
- 回滚：从 `pdf2zh.service` 去掉该 ExecStartPre，重装 `pdf2zh-next` 或从备份还原 `gui.py`，再按 [`pdf2zh-patch-order.md`](../contracts/pdf2zh-patch-order.md) 重放 1–30
- 旧任务/下载不依赖 050 DOM，回滚后 040 登录与预览仍可用

## 未解决风险

- 浏览器自动化截图 CJK 字体缺失，视觉以人工 Chrome 为准
- 对象级单元格/OCR 框编辑仍走既有 BabelDOC 能力，检查器是入口不是新引擎
- 语义 TM 不自动 reuse（PLAN-055 边界）
