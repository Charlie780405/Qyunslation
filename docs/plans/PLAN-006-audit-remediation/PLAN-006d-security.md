# PLAN-006d：安全加固

- TLS 默认校验 + `TLS_VERIFY` 开关
- 可选 `API_TOKEN` Bearer 鉴权
- task_id 扩至 16 hex；Zip Slip 防护；json/srt 模板 XSS
- CORS 默认 localhost；MCP 路径/URL 白名单；Docker 去掉默认 `--with-mcp`
- API Key 改 sessionStorage；去掉硬编码内网默认值
