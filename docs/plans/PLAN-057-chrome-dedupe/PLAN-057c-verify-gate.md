# PLAN-057c：门禁

> 父计划：[PLAN-057](./PLAN-057-chrome-dedupe.md)

## 验收

```bash
bash scripts/verify-plan-050.sh
bash scripts/verify-plan-057.sh
```

| 组 | 判据 |
| --- | --- |
| 静态 | 057 目录、索引、无帮助 Accordion、有 lang-row visible=False、有 55vh 覆盖 |
| pytest | test_plan057 |
| 现网 | gui 有 057 标记；登录后 HTML 无双 Accordion 标题常驻 |
| 浏览器 | 去重 + 高级可滚 |

## 完成定义

- [x] `SUMMARY: PASS fail=0`
- [x] WT-057 有点验证据
