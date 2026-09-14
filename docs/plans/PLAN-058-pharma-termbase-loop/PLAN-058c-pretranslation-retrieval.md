# PLAN-058c：译前确定性解析与混合检索

> 父计划：[PLAN-058](./README.md)

## 交付

- 规范化索引、最长词组匹配、词边界和 LRU 任务缓存。
- preferred、synonym、abbreviation 命中统一走本地 exact/alias 快路径。
- 未命中才调用 bge-m3；语义结果保留为 suggestion，`hard_constraint=false`。
- 将确认词编译为只读术语策略包，注入正文、表格、脚注和图片 OCR 所使用的翻译参数边界。

## 完成定义

- 精确/别名解析不触发 embedding monkeypatch。
- 项目词条覆盖临床词条；不同项目可独立使用不同译法。
- 模型缓存和翻译缓存均带 termbase 版本。
