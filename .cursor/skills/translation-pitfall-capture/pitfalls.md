# 踩坑（SK-Q008）

1. **靠自觉写 pitfalls → 从不写** — 必须有机械装置：签名表 + capture + hook。
2. **签名用内部术语 → 用户原话命不中 skill** — description 必须含症状原话。
3. **promote 不写 registry 审计行 → 体系漂移** — `--promote` 必须双写。

4. **SIG-INBOX-UNMATCHED（2026-09-12）** — verify-047 合成 unknown ERROR 进 inbox；promote 清待归档，勿把 `totally_unknown_widget_xyz` 写入签名表否则 inbox 断言失败
