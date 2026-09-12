# WT-047 文献译文交付闭环

## 实现摘要

- 047a/b：双服务部署脚本、sidecar 指纹门禁、`X-Image-QC` + `qc_channel`
- 047c：停止把 overflow 折进 fit；`min_scale=0.12`；pdf_creater unicode 兜底
- 047d：段落合并放宽 + 段间距收缩 + 剂量/药名 sanitize
- 047e：列簇门禁松绑 + `pdf_table_normalize`
- 047f：竖排聚合、面板统一字号、擦除覆盖率、字号下限
- 047g：SK-Q004–Q008 + capture + hooks

## 验收

```bash
bash scripts/deploy-translate-stack.sh
bash scripts/verify-plan-047.sh
```

样本重跑（人工）：上传 `ljae439`，确认摘要/目的出现、表区字号种类≤3、竖排旋转、imgtr `qc_channel=sidecar`。

## 实测

| 项 | 结果 |
| --- | --- |
| verify-plan-047 | PASS blocked=1 fail=0（样本 env 未设） |
| sidecar 指纹 | 一致（部署脚本 PASS） |
| 双服务 | pdf2zh + qyunslation-office active |
| Skill | SK-Q004–Q008 已登记；capture inbox 可用 |
