---
name: translation-pitfall-capture
description: >-
  踩坑自动沉淀：错误签名表、capture 脚本、hooks、pitfalls-inbox。
  触发：沉淀、固化 skill、踩坑、error-signatures、pitfalls-inbox、promote、
  跑完验收、PLAN-047g、SK-Q008。
---

# 踩坑自动沉淀（SK-Q008）

## 通用原则

1. **触发词用用户的症状语言，不用内部术语。** description 里要有「改了没效果」「依然如故」「译文丢了」这类原话。
2. **每条铁律必须带「首查」和「判据」。** 症状 / 先查 / 修法 / verify 四列，否则铁律退化成口号。
3. **一个坑只有一个 canonical 归属。** 竖排聚合→SK-Q002；区域字号归一→SK-Q003。
4. **诊断三问**（见 SK-Q004/005）：代码在哪个进程？失败是难看还是消失？谁会告诉我？

## 机制

```
作业日志 + imgtr.json + verify 输出
        │
        ▼
skill-pitfall-capture.py
        │
   ┌────┴────┐
   │命中签名 │未命中 → pitfalls-inbox.md（待归档）
   │只计数   │
   └────┬────┘
        ▼
--promote <SIG> --skill <SK-ID>
        │
        ▼
目标 pitfalls.md + registry 审计行
```

## 铁律

1. **跑一次验收 = 沉淀一次**——`verify-plan-047.sh` 末尾调用 capture。
2. **未知 ERROR 必须进 inbox**，不得静默丢弃。
3. **`--promote` 才写入正式 skill**，并同步 registry 审计表。
4. **裸 restart pdf2zh 被 hook 拦截**，提示 `deploy-translate-stack.sh`。

## 相关文件

- `.cursor/skills/skill-registry/error-signatures.toml`
- `.cursor/skills/skill-registry/pitfalls-inbox.md`
- `scripts/skill-pitfall-capture.py`
- `.cursor/hooks.json` / `.cursor/hooks/*`
