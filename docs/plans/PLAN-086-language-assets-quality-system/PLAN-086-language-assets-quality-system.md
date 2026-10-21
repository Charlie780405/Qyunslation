# PLAN-086：Qyunslation 术语库、错法表与风格指南质量系统

## 目标与边界

把术语库、风格指南和错法表保持为三类独立、可审计的语言资产，并在翻译开始时编译为不可变 bundle。首发采用受控人工导入；不做外部定时同步、不自动晋升模型建议、不在未授权时携带 MedDRA/CDISC 等受限数据。

## 已实现接口

- `GET /api/v1/language-assets/releases`
- `GET /api/v1/language-assets/releases/{id}` 与 `/diff`
- `POST /api/v1/language-assets/imports/preview`
- `POST /api/v1/language-assets/imports/{id}/apply`
- `POST /api/v1/language-assets/releases/{id}/publish`
- `POST /api/v1/language-assets/releases/{id}/rollback`
- `GET/POST/PATCH /api/v1/style-profiles`
- `POST /api/v1/style-profiles/{id}/publish`
- `GET/POST/PATCH /api/v1/quality-rules`
- `POST /api/v1/quality-rules/{id}/publish`

所有写接口要求 `term_admin/admin/owner`，导入按 SHA-256 幂等，原始内容在应用后清除，审计保留来源摘要、许可和哈希。发布版本不可修改；新的编辑会产生新版本。

## 数据与运行时

`language_asset_release` 与 `language_asset_release_item` 保存不可变发布快照；`style_profile` 和 `quality_rule_definition` 保存可编辑草稿；`language_asset_import_batch` 保存受控导入批次。翻译任务的 `settings_snapshot.language_assets` 保存选中的 release id/version/content hash 和 `bundle_hash`，QA 从同一快照读取错法规则。

## 验收与剩余门禁

已通过后端 API、迁移、租户隔离、导入幂等、前端 type-check、235 个前端测试和生产构建。上线前仍须用专家盲评双语金标确认高风险术语准确率、错法规则 precision/recall、阻断逃逸率、误阻断率、延迟和 token 成本，并以 `shadow → pilot → on` 分阶段切换；异常时恢复到上一发布版本或关闭资产 QA 模式。
