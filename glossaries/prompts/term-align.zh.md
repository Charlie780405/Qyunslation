你根据完整原文段与对应完整译文段，抽出指定术语的双语对齐。

对每个术语返回：
- source_term
- observed_target：必须是该段译文里的原文片段；找不到则空字符串
- suggested_target：规范中文译法，可以与实际译文不同
- confidence：0 到 1

禁止编造数字、单位或译文中不存在的片段。只输出 JSON 数组。
