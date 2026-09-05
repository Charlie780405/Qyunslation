# WT-005b Word sidecar

**日期：** 2026-08-23  
**状态：** 已部署

## 变更

| 项 | 内容 |
| --- | --- |
| unit | `qyunslation-office.service` → `127.0.0.1:8010` |
| env | `/home/dev/pdf2zh/office.env`（35b / temp=0 / concurrent=4 / OFFICE_LOCK） |
| import | `docutranslate` → symlink `qyunslation`（原 editable 指向已删路径） |
| Caddy | 公网统一 `translate.qyunsgen.com` → :7860；Word/图经 pdf2zh 内路由到 sidecar :8010 |
| homepage | 「翻译 Qyunslation」卡片 → `https://translate.qyunsgen.com` |

## 验收

- `curl 127.0.0.1:8010` 200（sidecar 本机）
- 公网入口：`https://translate.qyunsgen.com`

## 回滚

`systemctl --user disable --now qyunslation-office`；pdf2zh 去掉 office-route 补丁后 restart。
