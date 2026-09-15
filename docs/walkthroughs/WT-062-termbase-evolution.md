# WT-062：术语工作台准确度与自动进化

> 计划：[PLAN-062](../plans/PLAN-062-termbase-evolution/README.md)

## 工程验证记录

| 项目 | 结果 |
| --- | --- |
| curated seed | 393 concepts |
| harvest 提升领域缩写 | EASI/IGA/BSA/SCORAD/NHS/tralokinumab 等 resolve 为 hard |
| 062-v1 规则 + 历史 purge | 累计 reject 噪声；现场二次 purge reject=19+46，pending 78 / 23 个不重复词 |
| `_window_cjk` 删除 + 段落对齐 | verify 专项通过 |
| curated miss → violation | 已入库词不再反复 pending |
| Concept 联想 / 下一条导航 / 进度区间 | 补丁在现场 `gui.py` |
| `verify-plan-062.sh` | PASS fail=0 |

## 已执行本地命令

```bash
.venv/bin/python scripts/plan034d-import-csv.py
.venv/bin/python scripts/plan062-purge-stale-candidates.py --apply
python3 scripts/apply-pdf2zh-docimg.py
python3 scripts/apply-pdf2zh-060-termbase-workbench.py
bash scripts/verify-plan-062.sh
bash scripts/deploy-translate-stack.sh
```

## 部署记录

- `deploy-translate-stack.sh`：pdf2zh + qyunslation-office `active`；sidecar 指纹 `7542777de0fd` 双侧一致。
- 现场缺口：旧 `gui.py` 缺 `_qy_tbl_progress` / `0.96 + 0.03`。`upgrade_post_if_stale` 已把缺进度回调视为 stale，ExecStartPre 重打后现场命中。
- 规则补缺：`ilumab` 一律按药物碎片排除；`TARGET`/`DERM`/`ADA`/`ACAD`/`DERMATOL`/`Inc`/`USA`/`MBA` 进 denylist。pending 不再含 `University` / `TSARTAI` / `300 mg` / `ilumab`。
- 重启后登录态失效，须重新登录。

## 浏览器实点（LIVE）

登录 `https://translate.qyunsgen.com/` 后可见「专业词汇 / 术语候选 / 实际译法 / 推荐译法 / 确认译法」；页面源码含「术语未遵循」「关联已有词条」。当前会话无已选文档，空态为「尚无可审校术语」。「需人工填写」只在有候选行时渲染。进度条、保存下一条须再译一篇真实文档补证。

剩余 pending 留给下次翻译走 screen/LLM：`EASI-50/90`、`PP-NRS`、`IL-4/13`、`dupilumab`、`ECZTEND`、`NCT*`、`CONSORT`、`IRB` 等。
