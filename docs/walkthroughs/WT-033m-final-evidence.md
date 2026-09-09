# WT-033m 终态证据与未关缺口收口

> 计划：[PLAN-033m](../plans/PLAN-033-pdf-fidelity/PLAN-033m-final-evidence.md)
> 分支：`feat/PLAN-033m-final-evidence`
> 基线：`origin/main`=`55ccbbb`
> 日期：2026-09-09
> 结论：**HEAD 绑定产物已重跑表格写出；`inspect_final` 对输出 PDF 做内容探针，`fail=[]`。** 合 main / 部署见文末。

## 产物

目录：`/tmp/plan033m-55ccbbb/`（含 `HEAD`）

| 文件 | 用途 |
| --- | --- |
| `*.zh.mono.pdf` / `*.zh.dual.pdf` | BabelDOC |
| `*.mono.imgtr.pdf` / `*.dual.imgtr.pdf` | 嵌图后处理 |
| `*.mono.imgtr.tbltr.pdf` / `*.dual.imgtr.tbltr.pdf` | 表格写出终态 |
| `033m-inspect.json` | 总门快照 |
| `table-zh-cache.json` | 单元格译文缓存（双语复用） |
| `tbltr-033m-c.log` | 本轮写出日志 |

样本：`/home/dev/.hermes/attachments/1-s2.0-S2666636725013958-main.pdf`  
SHA-256 `c88ea994746e13904ed012943130896426b8812f939ae14917e1c48f59b2f8dc`。禁止入库。

模型：`qwen3.6:35b-a3b` @ `http://100.67.66.123:11434/v1`（`office.env`）。  
`model_trace` 已写入执行 Manifest。

## 原始失败项

| 项 | 取证 | 本轮 |
| --- | --- | --- |
| Table 1 整表并成 1–2 格 | 侧放 `dir` 未建局部坐标；扫描器 1.5.0 缓存 2 块 | 扫描器 **1.6.0**；470 格 / 19×26；表区 CJK=417 |
| Table 2–4 整行/整表 | 单链容差把密表并成一格 | 自适应间隙切轴：53 / 123 / 59 格 |
| tbltr 软吞 | GUI `表格写出跳过` | `apply-pdf2zh-docimg.py` 失败 `raise`；现场 GUI 已打补丁 |
| execution PENDING | `put_execution` 无 `terminal` | 未达对象 SKIP + `terminal=true` |
| model_trace 未绑 GUI | 只靠后处理 env | `bind_task_model_trace` |
| Appendix 后误标参考文献 | `in_references` 跨页 sticky | `is_section_break` 关区 |
| 旧 staging 冒充金样 | `/tmp/plan033-staging` | 必须 `/tmp/plan033m-<HEAD>/` |
| Table 1 页仍英文 | 窄格 `ROLE_SIZE_DRIFT` 硬失败；侧放 OVERFLOW 只进续页 | 表角色不再统一字号；侧放最小号仍落字 |
| 图终态被表回写冲掉 | tbltr 用新扫描全员 PENDING→SKIP | `merge_prior_execution` 保留 FIGURE/IMAGE |
| 参考文献 DOI 假红 | 续页顶掉 dual 末三页 | 在含 REFERENCES 的页上数 DOI |

未做：`cap_body_gap` 进 BabelDOC（本轮粗体抽样已过）；Camelot / 整表栅格化；030h D1–D5。

## 门禁

| 门禁 | 结果 |
| --- | --- |
| verify-plan-033m.sh | PASS |
| inspect_final | `blocked=[]` `fail=[]` |
| verify-plan-028.sh | PASS |
| verify-plan-029.sh | PASS |
| verify-plan-033.sh | **PASS** fail=0（033a–e/g–m + structure suite） |
| verify-plan-030e.sh | 结构套件 PASS；嵌套 030d 金样曾要求参考文献 BODY 也是 `babeldoc_text_layer`（033h 起即为 PRESERVE）。已改为只断言 `semantic_scope!=references`，金样脚本 `gold_ok` |

`inspect_final` 通过项含：`table1_cells=470`、`table_region_cjk:table:1=417`、四表 TRANSLATED、两图 TRANSLATED、`references_doi=12`、`model_trace`。

保护：未改、未提交 `glossaries/auto-proper-nouns.csv`。

## 回滚

工作区未合 main。丢弃本分支即可回到 `55ccbbb`。

现场 GUI 若已打 033m 补丁：用 `/home/dev/pdf2zh/bak-plan033-tbltr-20260909T154000Z-gui.py` 或再跑 `scripts/apply-pdf2zh-docimg.py`。  
BabelDOC 四文件补丁签名见 `033m-inspect.json` `patch_signature`。
