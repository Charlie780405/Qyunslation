# PLAN-002g：翻译检索 UI 卡片

## 交付

| 位置 | 内容 |
|---|---|
| `knowledge.qyunsgen.com/` | 首页卡片网格，「翻译检索」Featured |
| `knowledge.qyunsgen.com/translations` | 专用检索页 + 跳转 translate |
| 顶栏 | 「翻译检索」导航 |
| `homepage.qyunsgen.com` | 「翻译检索」产品卡 → `/translations` |
| API | `GET /api/v1/search?prefix=10-Source-Documents/Translations` |

## 验收

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:6202/translations
curl -fsS 'http://127.0.0.1:6201/api/v1/search?q=PDF&prefix=10-Source-Documents/Translations'
```
