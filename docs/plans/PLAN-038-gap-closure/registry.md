# PLAN-038 缺口登记表（SSOT）

> 状态字段：`open` | `closed` | `wontfix`
> 关闭证据：WT 路径 + verify 命令；子计划收口时同批回写来源文档。

| G-ID | 严重度 | 归属 | 状态 | 来源 | 摘要 | 关闭证据 |
| --- | --- | --- | --- | --- | --- | --- |
| G-DOC-001 | P2 | 038a | closed | docs/plans/PLAN-035-table-execution-fidelity/PLAN-035a-digit-token-policy.md | 035a 头仍「实施中」 | WT-038a / verify-plan-038.sh |
| G-DOC-002 | P2 | 038a | closed | docs/plans/PLAN-035-table-execution-fidelity/PLAN-035b-digit-execution-audit.md | 035b 头仍「实施中」 | WT-038a / verify-plan-038.sh |
| G-DOC-003 | P2 | 038a | closed | docs/plans/PLAN-035-table-execution-fidelity/PLAN-035c-cross-page-scan.md | 035c 头仍「实施中」 | WT-038a / verify-plan-038.sh |
| G-DOC-004 | P2 | 038a | closed | docs/plans/PLAN-035-table-execution-fidelity/PLAN-035d-cross-page-exec-verify.md | 035d 头仍「实施中」 | WT-038a / verify-plan-038.sh |
| G-DOC-005 | P2 | 038a | closed | docs/plans/PLAN-036-table-policy-unification/PLAN-036a-policy-ssot-refactor.md | 036a–d 头仍「待批准」 | WT-038a / verify-plan-038.sh |
| G-DOC-006 | P2 | 038a | closed | docs/plans/PLAN-033-pdf-fidelity/PLAN-033g-execution-contract.md | 033g–l 头滞后 | WT-038a / verify-plan-038.sh |
| G-DOC-007 | P2 | 038a | closed | docs/walkthroughs/WT-033n-head-evidence-rebind.md | WT-033n 过时「030 未关→030j」 | WT-038a / verify-plan-038.sh |
| G-DOC-008 | P1 | 038b | closed | docs/walkthroughs/WT-036-table-policy-unification.md | 037 已实现无独立 PLAN/WT | WT-038b / WT-037 / verify-plan-037 |
| G-DOC-009 | INFO | 038a | closed | docs/contracts/visual-gold-030.md | 视觉金样三项待人工批准 | WT-030i / visual-gold-030 @ e19e686 |
| G-DOC-010 | P2 | 038a | closed | docs/plans/PLAN-036-table-policy-unification/PLAN-036-table-policy-unification.md | 036e 无独立文件，须在父纲领补节 | WT-038a / verify-plan-038.sh |
| G-DOC-011 | P2 | 038a | closed | docs/plans/PLAN-001-delivery-gpu-audit/PLAN-001-delivery-gpu-audit.md | 001 应标被 002 取代关闭 | WT-038a / verify-plan-038.sh |
| G-DOC-012 | P2 | 038a | closed | docs/plans/PLAN-003-translate-throughput/PLAN-003-translate-throughput.md | 003/004/013/031 关闭字段滞后 | WT-038a / verify-plan-038.sh |
| G-DOC-013 | P2 | 038a | closed | docs/plans/PLAN-030-semantic-layout-translation/PLAN-030d-manifest-ssot-execution-parity.md | 030d 头仍「实施中」 | WT-038a / verify-plan-038.sh |
| G-DOC-014 | INFO | 038a | closed | docs/walkthroughs/WT-017-dual-preview.md | WT-017 空 hash | WT-038a（注明历史未填，不臆造） |
| G-OPS-001 | P0 | 038c | closed | docs/walkthroughs/WT-002-babeldoc-replace-translate.md | docutranslate.service 待 disable | WT-038c（is-enabled=disabled） |
| G-OPS-002 | P0 | 038c | closed | docs/walkthroughs/WT-032-archive-hygiene.md | 归档 10 条脏名未 --apply | WT-038c（--apply 11 条） |
| G-OPS-003 | P1 | 038c | closed | docs/walkthroughs/WT-035-table-execution-fidelity.md | STRICT_SAMPLE 可选 | WT-038c（文档化；本机未强制） |
| G-OPS-004 | P1 | 038c | closed | docs/walkthroughs/WT-035-table-execution-fidelity.md | scanner 1.7.0 需重新预扫说明 | WT-038c / WT-035 |
| G-OPS-006 | INFO | 038c | closed | docs/walkthroughs/WT-031-repo-governance.md | 旧恢复分支是否删除 | WT-038c（已删 recovery-030e，0 ahead） |
| G-CAP-001 | P1 | 038d | closed | docs/walkthroughs/WT-030-table-closure.md | 纯图片表 cell 网格 | WT-038d / verify-plan-038d.sh |
| G-CAP-002 | P1 | 038e | closed | docs/walkthroughs/WT-036-table-policy-unification.md | PPT picture OCR | WT-038e / verify-plan-038e.sh |
| G-CAP-003 | P2 | 038f | wontfix | docs/walkthroughs/WT-033n-head-evidence-rebind.md | cap_body_gap 进 BabelDOC | WT-038f（不 fork BabelDOC） |
| G-CAP-004 | P2 | 038f | closed | docs/walkthroughs/WT-033n-head-evidence-rebind.md | Figure 像素残影探针 | WT-038f / verify-plan-038f.sh |
| G-CAP-005 | P2 | 038g | closed | docs/walkthroughs/WT-031-repo-governance.md | Gradio 全面白牌 | WT-038g / apply-pdf2zh-brand.py |
| G-CAP-006 | P2 | 038g | closed | docs/plans/PLAN-002-babeldoc-replace-translate/PLAN-002-babeldoc-replace-translate.md | --auth-file 登录墙 | WT-038g / auth.csv+config |
| G-CAP-007 | P2 | 038g | closed | docs/walkthroughs/WT-002-babeldoc-replace-translate.md | 手动术语表 --glossaries | WT-038g / config glossaries |
| G-CAP-008 | P2 | 038g | closed | docs/walkthroughs/WT-003-translate-throughput.md | 多租户 unload 互取消 | WT-038g / apply-pdf2zh-038g-session-cancel.py |
| G-CAP-009 | P2 | 038g | closed | docs/plans/PLAN-035-table-execution-fidelity/PLAN-035-table-execution-fidelity.md | DOCX/PPTX 跨页续表 | WT-038g（DOCX closed；PPTX wontfix） |
| G-CAP-011 | WONTFIX | 038e | wontfix | docs/plans/PLAN-030-semantic-layout-translation/PLAN-030g-pptx-dual-mode-closure.md | SmartArt/Chart/OLE | PLAN-030g OOS |
| G-WONT-001 | WONTFIX | 038a | wontfix | docs/plans/PLAN-001-delivery-gpu-audit/PLAN-001-delivery-gpu-audit.md | 001 GPU/旧入口质量门 | 被 002 取代 |
| G-WONT-002 | WONTFIX | 038a | wontfix | docs/walkthroughs/WT-004c-llm-batch.md | 004c 批推理已回滚 | WT-004c |
| G-WONT-003 | WONTFIX | 038a | wontfix | docs/walkthroughs/WT-004d-vllm-gate-closed.md | 004d 同权 vLLM 不做 | WT-004d |
| G-WONT-004 | WONTFIX | 038a | wontfix | docs/plans/PLAN-027-doc-image-translation/PLAN-027-doc-image-translation.md | EMF/WMF / DrawingML 矢量 | PLAN-027 OOS |
| G-WONT-005 | WONTFIX | 038a | wontfix | docs/plans/PLAN-020-stuck-spinner/PLAN-020-stuck-spinner.md | Cloudflare 上传带宽 | PLAN-020 |
| G-WONT-006 | WONTFIX | 038a | wontfix | docs/walkthroughs/WT-030-table-closure.md | 不提交 auto-proper-nouns.csv | 策略 |
| G-WONT-007 | WONTFIX | 038a | wontfix | docs/plans/PLAN-030-semantic-layout-translation/PLAN-030i-delivery-closure.md | CONDITIONAL 格式进 GUI | 030i OOS |
| G-WONT-008 | WONTFIX | 038a | wontfix | docs/walkthroughs/WT-033d-references.md | BabelDOC IL 参考文献禁译 | manifest skip |
