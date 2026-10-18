# 业务 PostgreSQL 绑定收口到 loopback（PLAN-077 T3）

> 状态：**已备好，未执行**——需用户确认窗口。不读取任何 `.env`。

## 只读证据（2026-10-18）

- `qyunslation-plan034c-pg`（`pgvector/pgvector:pg16`，Compose project `qyunslation`，`/home/dev/qyunslation`）发布为 `0.0.0.0:5433->5432` 与 `[::]:5433`，已运行 2 周且 healthy。
- 主机有公网网卡 `enp1s0`（公网地址）和 `tailscale0`；`ufw`/`iptables` 需要 sudo，**我无法读取防火墙状态**，所以不能证明 5433 没有对公网开放。
- 当前连接（`ss`）全部来自 127.0.0.1，对端进程是本机 `qyunslation` 服务；`pg_stat_activity` 里的客户端是 docker 网桥网关地址（容器 NAT 的本机源）。没有发现远程消费者。
- 该库有一个排序规则版本告警（建库 2.41，系统 2.36），与本任务无关，登记为遗留项。

## 变更内容（一行）

`docker-compose.plan034c.yml`：

```diff
-      - "5433:5432"
+      - "127.0.0.1:5433:5432"
```

本机服务继续用 `127.0.0.1:5433` 连接，不需要改任何应用配置。

## 执行步骤（用户执行，只重启本仓 PG）

1. 备份：`docker exec qyunslation-plan034c-pg pg_dump -U qyunslation -Fc qyunslation > <备份目录>/qyunslation-$(date +%F).dump`，并 `pg_restore --list` 校验非空。
2. 备份当前 Compose：`cp docker-compose.plan034c.yml docker-compose.plan034c.yml.bak-$(date +%F)`。
3. 应用上面的 diff，`docker compose -f docker-compose.plan034c.yml config | grep -A2 ports` 确认是 `127.0.0.1`。
4. 仅重建该服务：`docker compose -f docker-compose.plan034c.yml up -d postgres`（数据卷 `plan034c_pgdata` 保留；服务有数秒中断，期间 qyunslation 的 DB 连接会重连）。
5. 验证：`ss -ltn | grep 5433` 只剩 `127.0.0.1:5433`；`alembic current` 与迁移前相同；`curl -fsS http://127.0.0.1:8010/` 正常；一次翻译任务预检通过。
6. 从外部网络（如手机热点）探测公网地址的 5433 应不可达。

## 回滚

还原 `.bak` 文件，重复步骤 4。数据卷未动，不需要数据回滚。

## 另请用户核实（我无法读取）

`QYUNSLATION_PG_PASSWORD` 在生产是否已设置为非默认值：compose 的默认值 `qyunslation_dev_only` 是公开的开发口令。如果生产没有覆盖它，在步骤 4 之前 5433 是否对公网可达就变成了紧急问题——请先确认防火墙，必要时先执行本变更，再更换口令。
