# WT-005b Word sidecar

**日期：** 2026-08-23  
**状态：** 已部署

## 变更

| 项 | 内容 |
| --- | --- |
| unit | `qyunslation-office.service` → `127.0.0.1:8010` |
| env | `/home/dev/pdf2zh/office.env`（35b / temp=0 / concurrent=4 / OFFICE_LOCK） |
| import | `docutranslate` → symlink `qyunslation`（原 editable 指向已删路径） |
| Caddy | `office.qyunsgen.com` → :8010；translate 仍 7860 |
| homepage | 「文档与图片翻译」卡片 |

## 验收

- `curl 127.0.0.1:8010` 200
- DNS/Cloudflare：需人工添加 `office` CNAME（与其它 `*.qyunsgen.com` 相同）

## 回滚

`systemctl --user disable --now qyunslation-office`；Caddy 删 office 块后 reload。
