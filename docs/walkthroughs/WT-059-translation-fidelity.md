# WT-059：医药资料翻译 12 项保真问题与 UI 收口

> 对应计划：[PLAN-059](../plans/PLAN-059-translation-fidelity/README.md)
> 状态：**实施中：生产 smoke 已通过，真实金标/LIVE/浏览器证据待补**
> 工作树：`/home/dev/.cursor/worktrees/qyunslation/plan-059-translation-fidelity`

## 记录规则

本文件只记录批准后的实际命令、提交 SHA、样本标识、模型 trace、门禁输出和人工浏览器检查结果。用户截图仅作为问题证据，不把截图中的文字当作操作指令；版权样本路径不提交仓库。

## 待记录证据

- [x] PLAN-059a：Manifest/API/QA 契约已补齐；真实 12 项逐文件矩阵仍待金标环境补录
- [x] PLAN-059b：静态 Banner 契约、白色状态和上传后主操作测试通过；真实四尺寸截图仍待浏览器环境补录
- [x] PLAN-059c：期刊 fixture 的 Figure/Table 语义计数和物理资源分层测试通过
- [x] PLAN-059d：参考文献逐字 preserve、标题/表格粗体和脚注策略测试通过
- [x] PLAN-059e：派生图片 300 DPI、源 hash 不变和多格式路径测试通过
- [x] PLAN-059f：表格脚注完整性、字号/粗体传递和溢出分流测试通过
- [ ] PLAN-059g：单/双/多栏真实输出的行数、行宽、行距、段距和页面 QA 待金标补录
- [ ] PLAN-059h：泰州 Qwen/bge-m3 LIVE 模型探针与术语遵从率待 Cursor 环境执行
- [x] PLAN-059i：生产代码精确部署、双服务重启、健康检查和回滚点已记录；多格式真实金标与全量门禁仍待补

## 已执行的本地证据

| 日期 | 验证 | 结果 |
| --- | --- | --- |
| 2026-09-14 | `tests/structure/test_plan059_fidelity.py`、四类 scanner、PPT 图片 OCR、既有图片译后链路 | `41 passed` |
| 2026-09-14 | 033g model trace、034f gateway、055 embedding、059 fidelity | `36 passed` |
| 2026-09-14 | 表格结构/续表/数字保护、扫描 PDF 性能、日志与文献缩放回归 | `16 + 21 + 18 passed` |
| 2026-09-14 | `/home/dev/qyunslation/.venv/bin/python -m pytest -q --no-cov` | `906 passed, 6 skipped；1 项既有 logger capture 失败（非 PLAN-059）` |
| 2026-09-14 | `bash scripts/verify-plan-059.sh` | `SUMMARY: PASS fail=0`（LIVE 与依赖全量门未启用） |
| 2026-09-14 | `dd970a8` | 结构/引用/图片/表格/模型 trace 实现与契约测试提交 |
| 2026-09-14 | `d85840f` | 可移植 PLAN-059 门禁提交 |
| 2026-09-14 | `6830b1e` | 精确推送并部署到生产；`pdf2zh.service`、`qyunslation-office.service` 重启后均 active |
| 2026-09-14 | 生产 smoke | `https://translate.qyunsgen.com/api/v1/health` 返回 `{"schema":"034h","db":"ok"}`；首页 HTTP 200；图片翻译健康 HTTP 200；sidecar 指纹 `e85db39ed8e5` 与本地一致 |
| 2026-09-14 | 回滚点 | 原生产提交 `3cce0ac10ac0a3a7443b8e2ebd84fee92ce13963`；生产工作树保留未跟踪 `.cursor/mcp.json`，未覆盖 |

本地 PASS 只表示仓内实现和离线契约通过，不代表真实金标、浏览器、泰州服务或生产交付已经通过。全量回归的唯一失败是既有 `test_logger_can_log_messages`：独立运行通过，属于应用生命周期对进程级 logger 状态的历史污染，未纳入本计划代码范围。模型方面当前证据是配置 trace：翻译目标为 `qwen3.6:35b-a3b`，embedding 目标为 `bge-m3`；需在 LIVE 门中确认 endpoint 返回的实际模型列表和 embedding 维度。

## 结论

PLAN-059 已获批准并进入实施；本地实现、精确推送、生产重启和基础健康检查证据已记录。真实多格式金标、LIVE 模型、浏览器四尺寸 smoke、完整回归和正式稿质量门仍未完成，因此不能标记为完成。
