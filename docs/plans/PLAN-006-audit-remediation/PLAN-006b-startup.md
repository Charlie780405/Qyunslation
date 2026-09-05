# PLAN-006b：启动加速

- 拆分 `ConverterDoclingConfig` 到轻量模块
- `MarkdownBasedWorkflow` 延迟加载 `ConverterDocling`
- 实测：import app **12.1s → 2.16s**（见 `docs/perf/baseline-006b.json`）
