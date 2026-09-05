# WT-010：扫描件版式保真通用化

## 做了什么

- OCR 盒去纵向重叠（`_deoverlap_boxes`）+ 微段落抑制，根治 2.4–6pt 碎字
- 角色感知聚合：正文可并段，落款/地址逐行；`signature_align=left`
- 图形区检测与译后回插（logo/印章）
- 专名表 + harvest identity；GenScend 等不再幻觉成「金斯瑞」
- bench V8 + `verify-plan-010.sh`；Skill SK-Q001

## 验收

```bash
bash scripts/verify-plan-010.sh after-f   # 28 pass
bash scripts/verify-skill-registry.sh     # 9 pass
```

交付物：`deliverables/plan-010-fidelity/letter.mono.pdf`（及 png）。

V8 要点：OCR 纵向重叠盒 = 0；落款逐行 + 偏右左齐；logo 回插；`江苏景行生物医药有限公司` / 无「金斯瑞」。

## 实现时补丁

- `insert_textbox` 扩盒必须受后继同列盒限制，否则 debug/BabelDOC 再次重叠
- 短行写不下时 `insert_text` 兜底（render_mode=3），避免 `placed=False` 丢专名/落款
- letter 去重叠用 `gap=0.5, min_h=12`，给中文排版留高度

## 踩坑沉淀

见 `.cursor/skills/scanned-doc-layout-fidelity/pitfalls.md`。
