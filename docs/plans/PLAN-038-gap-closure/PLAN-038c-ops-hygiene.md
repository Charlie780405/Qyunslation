# PLAN-038c：运维卫生

> 状态：**已完成**
> 父计划：[PLAN-038](./PLAN-038-gap-closure.md)
> 归属缺口：G-OPS-001…004、G-OPS-006
> 验收：[WT-038c](../../walkthroughs/WT-038c-ops-hygiene.md)


## 命令清单

```bash
# G-OPS-001（需 sudo）
sudo systemctl disable --now docutranslate.service

# G-OPS-002（先备份；脚本 --apply 内建备份）
QYUNSLATION_VERIFY_PY=/home/dev/qyunslation/.venv/bin/python \
  /home/dev/qyunslation/.venv/bin/python \
  /home/dev/qyunslation/scripts/fix-archive-filenames.py --apply

# G-OPS-003（可选；无 033 样本机保持 BLOCKED）
# 写入 office/pdf2zh 环境：QYUNSLATION_RELEASE_STRICT_SAMPLE=1

# G-OPS-004：文档说明——scanner 1.7.0 后同一 PDF 须重新预扫
```

## 规则

- 无 sudo / 未确认时条目保持 `open`，不得假装关闭
- G-OPS-006（旧分支删除）默认 INFO，需人工决定

## 验收

- 已执行项：registry + 来源 WT 同批回写
- `systemctl is-enabled docutranslate.service` → disabled 或 not-found（若已关）
