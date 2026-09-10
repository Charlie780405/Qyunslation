# PLAN-041e：金标、性能与交付

> 状态：**待执行**
> 父计划：[PLAN-041](./PLAN-041-pdf-regulatory-form-fidelity.md)

## 实施

1. 增加不含真实姓名、电话、邮箱和机构地址的匿名合成 PDF/内存夹具。
2. `scripts/verify-plan-041.sh` 默认仓库 `.venv`，允许 `QYUNSLATION_VERIFY_PY` 覆盖。
3. 实样仅由 `QYUNSLATION_PLAN041_SAMPLE` 定位；校验 SHA-256 可选，缺样本则 `BLOCKED`。
4. 记录 7 页表格金标、CJK 残留、不可变 token、字号、粗体、视觉渲染和扫描耗时。
5. 回归 structure 全量、PLAN-028、PLAN-033/035/036 相关门禁。
6. 新增仓库 Skill `pdf-regulatory-form-fidelity`，登记为 `SK-Q003`。
7. 所有门禁通过后更新部署补丁序、应用生产补丁并重启验证；失败则保留分支证据，不宣称上线。

## 交付

- `scripts/verify-plan-041.sh`
- `docs/walkthroughs/WT-041-pdf-regulatory-form-fidelity.md`
- `.cursor/skills/pdf-regulatory-form-fidelity/`
- 原子提交并推送 `feat/PLAN-041-pdf-regulatory-form-fidelity`
