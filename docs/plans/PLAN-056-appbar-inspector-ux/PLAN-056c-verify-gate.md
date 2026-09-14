# PLAN-056c：门禁

> 父计划：[PLAN-056](./PLAN-056-appbar-inspector-ux.md)

## 验收

```bash
bash scripts/verify-plan-050.sh
bash scripts/verify-plan-056.sh
# 可选 LIVE：
# QYUNSLATION_PLAN056_LIVE=1 bash scripts/verify-plan-056.sh
```

| 组 | 判据 |
| --- | --- |
| 静态 | 056 目录、索引行、无 `translateX(100%)`、有 `qy_dir`/Accordion |
| pytest | 补丁断言 056 控件与无抽屉 CSS |
| 现网 | `gui.py` 编译；登录后 HTML 含 `英→中` |
| 浏览器 | 检查器可见、方向双向同步、帮助可开合、强制刷新不白屏 |
| 部署 | 仅 `deploy-translate-stack.sh` |

## 完成定义

- [x] `SUMMARY: PASS fail=0`（或明确 BLOCKED，无 FAIL）
- [x] WT-056 有部署与点验证据
