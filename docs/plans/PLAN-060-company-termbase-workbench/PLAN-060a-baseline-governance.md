# PLAN-060a：基线、公司共享项目与权限治理

> 父计划：[PLAN-060](./README.md)

- 每个租户按固定 slug 创建或复用 `company-termbase` 项目，运行任务和 Concept 均落在此项目，禁止跨租户检索。
- 运行记录保存用户、源文件 SHA-256、格式、语言方向、Job、术语策略版本和生命周期；所有开始、完成与裁决写入审计事件。
- 普通成员可批准低风险项目候选；高风险只可 `submit_for_admin`。客户端和 API 没有自助升权接口。
- 受保护的主机脚本 `scripts/manage-term-admin.py` 以独立部署令牌和交互式输入授予/撤销 `term_admin`，并记录审计。
