# PLAN-060f：验证、部署与交付

> 父计划：[PLAN-060](./README.md)

1. 运行 `bash scripts/verify-plan-060.sh`，再执行 `QYUNSLATION_PLAN060_FULL=1` 的依赖门。
2. 部署前在两个服务共同读取的受保护环境文件中设置 `QYUNSLATION_TERM_BRIDGE_SECRET`、`QYUNSLATION_WORKBENCH_TENANT`；不要提交真实值。
3. 先执行 Alembic、验证 Caddy 没有 `/internal/workbench` 路由，再重启 sidecar 与 pdf2zh 服务。失败时停止并回滚到前一部署提交。
4. 用已登录用户在 320/768/1024/1440 宽度验证快速徽标、专业面板、上传和翻译操作均可用；以真实多格式文件验证下一文件精确复用且不调用 bge-m3。
5. 将测试、迁移、浏览器截图/结论、Caddy 负向断言、模型 LIVE 与提交 SHA 写入 WT；任一 FAIL/BLOCKED 不得宣称完成。
