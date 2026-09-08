<p align="center">
<img src="./qyunslation/static/quanxin-logo.svg" alt="荃信" width="220">
</p>

<h1 align="center">Qyunslation</h1>

<p align="center">荃信内部文档翻译 · 派生自 <a href="https://github.com/xunbu/docutranslate">DocuTranslate</a>（MPL-2.0）</p>

<p align="center">
  <a href="/README_ZH.md"><strong>简体中文</strong></a>
  · <a href="/README.md"><strong>English</strong></a>
  · <a href="./NOTICE.md">NOTICE</a>
  · <a href="./LICENSE">LICENSE</a>
</p>

Python 包与 CLI 为 `qyunslation`。线上：[https://translate.qyunsgen.com](https://translate.qyunsgen.com)（Caddy → pdf2zh `:7860` + sidecar `:8010`）。

## 出处

本仓是 [xunbu/docutranslate](https://github.com/xunbu/docutranslate) 的内部派生，连同 git 历史导入。GitHub Contributors 是历史作者，不是外邀开发者。详见 [NOTICE.md](./NOTICE.md)。

## 启动

```bash
uv sync
uv run qyunslation -i
uv run qyunslation -i --host 0.0.0.0
```

环境变量：`QYUNSLATION_*` 优先，仍双读 `DOCUTRANSLATE_*`。模板见 [`.env.example`](./.env.example)。

## MCP

```bash
uv sync --extra mcp
uv run qyunslation --mcp
```

见 [qyunslation/mcp/README.md](./qyunslation/mcp/README.md)。

## 测试

```bash
uv sync --group dev
uv run pytest tests/ -v
```

## 许可

MPL-2.0。保留上游版权声明。
