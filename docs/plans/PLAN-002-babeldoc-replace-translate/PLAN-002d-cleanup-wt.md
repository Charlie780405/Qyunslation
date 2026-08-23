# PLAN-002d：停旧服务、homepage 文案、WT

> 父纲领：`PLAN-002-babeldoc-replace-translate.md`
> 状态：已完成 | 2026-08-23

## 目标

去掉空转的 DocuTranslate unit 和孤儿 Qyunslation 进程；homepage 文案与实现一致；写 WT-002。

## 上一子计划缺口分析

002c 公网 V4/V5 通过后才执行。

## Out of Scope

- 删除 `/home/dev/qyunslation` 或 git 历史
- 迁移 `DT-2026-*` 归档进 pdf2zh
- 重做荃信白牌

## Task D1 — 停 :8010

```bash
ss -lntp | rg 8010
# 对 qyunslation PID 发 SIGTERM
ss -lntp | rg 8010   # 应无输出
```

## Task D2 — 禁 `docutranslate.service`

```bash
sudo systemctl disable --now docutranslate.service
systemctl is-enabled docutranslate.service
```

## Task D3 — homepage 文案

`/home/dev/homepage/config/services.yaml`：

- `href` / `siteMonitor` **保持** `https://translate.qyunsgen.com`
- 标题改「翻译 BabelDOC」
- `description: PDF 保留排版 · translate.qyunsgen.com`

重启 homepage 容器（若配置热加载不生效）：

```bash
docker restart qyunsgen-homepage
```

## Task D4 — verify + WT

```bash
bash scripts/verify-plan-002.sh after-d
```

写 `docs/walkthroughs/WT-002-babeldoc-replace-translate.md`，回填纲领 V1–V7。

## 验证清单

| # | 步骤 | 预期 |
| --- | --- | --- |
| D-V1 | `docutranslate.service` | inactive + disabled |
| D-V2 | `:8010` | 无监听 |
| D-V3 | 公网翻译 | 仍是 pdf2zh |
| D-V4 | WT-002 | 回填 V1–V7 |

## 回滚

保留 qyunslation 目录即可按纲领回滚节拉起 :8010。
