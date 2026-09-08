<p align="center">
<img src="./qyunslation/static/quanxin-logo.svg" alt="QYuns" width="220">
</p>

<h1 align="center">Qyunslation</h1>

<p align="center">荃信内部文档翻译 · 派生自 <a href="https://github.com/xunbu/docutranslate">DocuTranslate</a>（MPL-2.0）</p>

<p align="center">
  <a href="/README_ZH.md"><strong>简体中文</strong></a>
  · <a href="/README.md"><strong>English</strong></a>
  · <a href="./NOTICE.md">NOTICE</a>
  · <a href="./LICENSE">LICENSE</a>
</p>

Local document translation for QYuns. The Python package and CLI are `qyunslation`. Production URL: [https://translate.qyunsgen.com](https://translate.qyunsgen.com) (Caddy → pdf2zh `:7860` + sidecar `:8010`).

## Origin

This repository is an internal derivative of [xunbu/docutranslate](https://github.com/xunbu/docutranslate). Git history was imported; GitHub Contributors are historical authors, not invited collaborators. See [NOTICE.md](./NOTICE.md).

## Quick start

```bash
# from a clone of this repo
uv sync
uv run qyunslation -i          # Web UI, default localhost
uv run qyunslation -i --host 0.0.0.0
```

Environment: `QYUNSLATION_*` wins; `DOCUTRANSLATE_*` still works (PLAN-006 dual-read). Copy [`.env.example`](./.env.example).

## MCP

```bash
uv sync --extra mcp
uv run qyunslation --mcp
```

Details: [qyunslation/mcp/README.md](./qyunslation/mcp/README.md).

## Tests

```bash
uv sync --group dev
uv run pytest tests/ -v
```

## Remotes (this machine)

| name | purpose |
|---|---|
| `origin` | `Charlie780405/Qyunslation` (this repo) |
| `qyunslation` | same URL (kept so other worktrees keep tracking) |
| `upstream` | `xunbu/docutranslate` (fetch only) |
| `mirror` | local bare mirror |

## License

MPL-2.0. Upstream copyright remains. Modifications in this tree are QYuns internal work.
