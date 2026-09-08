# PLAN-031c 用户可见品牌收口

## 目标

人看到的产品名改为 Qyunslation；需要出处时写「派生自 / based on DocuTranslate」。不改 import 与环境变量名。

## 变更清单

| 路径 | 操作 |
|---|---|
| `README.md` / `README_ZH.md` | 重写为内部说明 |
| `README_JP.md` / `README_VI.md` | 改为短跳转 |
| `DocuTranslate.png/.ico/.icns` | 移入 `archive/legacy/` |
| i18n（static + frontend/public） | `pageTitle`、教程欢迎语、贡献文案 |
| `ContributorsContent.vue` | 去掉上游 PR/Issue/QQ，改为内部说明 |
| `qyunslation/cli.py` / `app.py` | 欢迎语 / 启动 print |
| `qyunslation/template/markdown.html` | 页脚 |
| `frontend/package.json` | `qyunslation-frontend` |
| `qyunslation/mcp/README.md` | 标题与安装命令 |
| `Dockerfile` | LABEL / 注释（保留 `DOCUTRANSLATE_PORT`） |
| `.env.example` | 仅文件头说明 |
| `tests/README.md` | 标题 |
| `full.spec` / `lite.spec` / `lite_mac*.spec` | 产出名；icon 改指 archive |
| `frontend/index.html.bak` | 删除 |

## 不做

- `DOCUTRANSLATE_*` 键名与 pytest `env`
- `archive/legacy/` 历史代码中的产品名
- PLAN/WT 史实字样
- `apply-pdf2zh-brand.py` 逻辑

## 验收

用户可见路径不再以 DocuTranslate 作为产品名；`pyproject.toml` 的 `name` 仍为 `qyunslation`。
