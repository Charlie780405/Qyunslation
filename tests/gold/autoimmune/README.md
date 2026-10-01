# 自免领域金标集（PLAN-073e）

10 份文献样本的结构化占位目录。每份样本包含：

- `source.txt`：英文原文片段
- `reference.zh.txt`：人工参考译文
- `required_terms.json`：必须命中的术语列表

`scripts/plan073-domain-eval.py` 读取本目录并输出术语准确率、药名漂移与 QA 误报率。
