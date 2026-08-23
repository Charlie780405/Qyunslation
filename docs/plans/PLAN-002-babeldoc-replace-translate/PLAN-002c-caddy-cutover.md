# PLAN-002c：Caddy 将 translate.qyunsgen.com 切到 pdf2zh

> 父纲领：`PLAN-002-babeldoc-replace-translate.md`
> 状态：已完成 | 2026-08-23

## 目标

homepage 卡片无需改 href：用户打开 `https://translate.qyunsgen.com` 看到 pdf2zh WebUI。

## 上一子计划缺口分析

002b 必须：7860 稳定、样张通过。否则禁止改 Caddy。

## 依赖 / 前置条件

- Caddy SSOT：`/home/dev/qyunsgen/config/Caddyfile-production-public`
- 改 Docker 单文件 mount 后 **必须** `docker restart qyunsgen-caddy`，不能只 reload
- `pdf2zh.service` 先 `enable --now`，再改 Caddy
- 翻译超时：现块 `read_timeout 600s` / `write_timeout 600s`，保留

## Out of Scope

- 改其它 `*.qyunsgen.com` 站点块
- 删 qyunslation 进程（002d）
- homepage href

## 关键决策

| # | 决策 | 理由 |
| --- | --- | --- |
| C1 | 只改 translate 块上游 `8010` → `7860` | 最小 diff |
| C2 | 证书/header/gzip 不动 | 复用通配 Origin 证书 |
| C3 | 先 enable pdf2zh，再 restart Caddy | 避免空窗 |

## 执行顺序（不可对调）

### Step 1 — enable pdf2zh

```bash
sudo systemctl enable --now pdf2zh.service
systemctl is-active pdf2zh.service
curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:7860/
```

### Step 2 — 改 Caddyfile

仅 `https://translate.qyunsgen.com` 块：

```diff
-# translate.qyunsgen.com — 本地文档翻译系统（DocuTranslate，阶段0-4）
-# 反代目标 127.0.0.1:8010 是宿主机 docutranslate 服务（systemd docutranslate.service）
+# translate.qyunsgen.com — PDFMathTranslate-next / BabelDOC
+# 反代目标 127.0.0.1:7860 是宿主机 pdf2zh.service
 reverse_proxy 127.0.0.1:8010 {
+reverse_proxy 127.0.0.1:7860 {
```

### Step 3 — 校验并重启

```bash
docker exec qyunsgen-caddy caddy validate --config /etc/caddy/Caddyfile
docker restart qyunsgen-caddy
docker exec qyunsgen-caddy grep -n '7860' /etc/caddy/Caddyfile
```

### Step 4 — 公网与回归

```bash
curl -sS https://translate.qyunsgen.com/ | rg '<title>'
curl -sS -o /dev/null -w '%{http_code}' https://table.qyunsgen.com/
curl -sS -o /dev/null -w '%{http_code}' https://knowledge.qyunsgen.com/
```

### Step 5 — 保留 :8010 回滚窗口

切流后 **先不杀** qyunslation，等 002d。

## 验证清单

| # | 步骤 | 预期 |
| --- | --- | --- |
| C-V1 | `bash scripts/verify-plan-002.sh after-c` | 全 PASS |
| C-V2 | homepage → 翻译卡 | 同域，新 UI |
| C-V3 | table/knowledge | 仍 200 |

## 回滚

Caddy 改回 `8010` + `docker restart qyunsgen-caddy`。

## 影响范围

全公司翻译入口；共享 Caddy 重启秒级中断其它站点。
