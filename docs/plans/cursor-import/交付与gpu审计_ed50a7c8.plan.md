---
name: 交付与GPU审计
overview: 对 Qyunslation（DocuTranslate 定制版）做一次全量技术审计，已定位 8 项交付断层与 9 项 GPU 利用缺陷（含"图片翻译硬编码模型名导致 Ollama 双份 16.6GB runner"、"concurrent=30 与 Ollama num_parallel 严重错配"、"文档内嵌图嵌字从未接入导出链路"），并按严重度拆为 5 个可独立验证的修复子计划。
todos: []
isProject: false
---

＃