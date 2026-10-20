# PLAN-080 灰度上线：四个默认关闭的开关

> 状态：**保留策略的修复已于 2026-10-20 部署并生效；四个开关均未开启。** 本文是开启它们的顺序、位置、判据和回滚方法。
> 所有改动在运行环境里执行，需要用户操作；仓库侧不改生产环境变量。

## 0. 先弄清什么已经生效

| 内容 | 生效方式 | 当前 |
| --- | --- | --- |
| 保留策略修复（编号问题不再被保留、正文长句不被当作署名/机构、职务保留、期刊引文不依赖标题与顺序） | 代码，下一次翻译即生效 | 已生效 |
| 字体补丁 `apply-pdf2zh-080c-fonts.py` | `pdf2zh.service` 的 `ExecStartPre` 写入引擎 | 已写入，开关关闭，输出不变 |
| 保留谓词告警（`_qy_033h_warn_once`） | `apply-pdf2zh-fidelity-033h.py` 在 `pdf2zh.service` 启动时升级引擎里的 helper | **待重启 pdf2zh 后生效**（`verify-plan-080.sh` 会提示 BLOCKED） |
| `QYUNSLATION_LAYOUT_QA`、`QYUNSLATION_DECORATION_REALIGN`、`QYUNSLATION_FONT_POLICY`（+`_FAMILY`）、`QYUNSLATION_OFFICE_PRESERVE` | 环境变量 | 均未设置（= off） |

## 1. 环境变量放在哪里

翻译 CLI 由 `qyunslation-office.service` 里的 runner 派生，继承它的环境；GUI 路径的翻译由 `pdf2zh.service` 派生。所以**两个服务都要设**，否则两条入口行为不一致。用 systemd drop-in，不要改主单元：

```ini
# ~/.config/systemd/user/qyunslation-office.service.d/plan080-flags.conf
# ~/.config/systemd/user/pdf2zh.service.d/plan080-flags.conf
[Service]
Environment=QYUNSLATION_LAYOUT_QA=on
```

应用：`systemctl --user daemon-reload && systemctl --user restart qyunslation-office.service pdf2zh.service`。
重启前确认没有进行中的翻译（重启会终止它们）：`ps -eo args | grep -E "pdf2zh_next --config|babeldoc"` 应为空，且 `var/translation-runs/*/*/*/state.json` 里没有 `translating` / `rendering` / `scanning`。`scripts/deploy-translate-stack.sh` 会做门禁、重启并核对指纹，建议用它而不是手动重启。

回滚：删除对应 drop-in，`daemon-reload` 并重启。不涉及数据，已经生成的产物不受影响。

## 2. 开启顺序与判据

| 步 | 开关 | 做什么 | 先决条件与判据 |
| --- | --- | --- | --- |
| 1 | `QYUNSLATION_LAYOUT_QA=on` | 只增加四类警告（整段仍为外文、参考文献被改写、字体种类过多、装饰线不对应），不改变任何产物 | 开启后观察 3–5 个真实作业。判据：`UNTRANSLATED_PARAGRAPH` 与 `REFERENCE_ENTRIES_CHANGED` 命中的页面经目视确认确是问题，误报比例可接受；`DECORATION_DANGLING` 和 `FONT_FAMILY_SPRAWL` 此时会如实报出现状，属预期 |
| 2 | `QYUNSLATION_DECORATION_REALIGN=on` | 译文产物里的下划线按译文文字裁短、挪位或删除；失败保留原文件 | 步骤 1 的 `DECORATION_DANGLING` 数应明显下降；任取 2–3 个产物逐页对比，文字逐页一致、没有表格线被改动；dual 产物若是交替页布局会被整体跳过（页数不一致），属预期 |
| 3 | `QYUNSLATION_FONT_POLICY=unified`（可选 `QYUNSLATION_FONT_POLICY_FAMILY=profile` 沿用画像里的黑体） | 简体中文译文统一用思源宋体 | 目视检查含表格、斜体引用、粗体标题的文档是否排版溢出；`FONT_FAMILY_SPRAWL` 应消失；目标语言为英文时策略不介入（有测试） |
| 4 | `QYUNSLATION_OFFICE_PRESERVE=on` | Word / PPT 正文与表格中的人名、职务、机构、引文原样保留 | 先用一份含参会人表格和参考文献的 Word 实测；该开关影响所有 Office 翻译，建议最后开 |

每一步之后运行（含真实样本）：

```bash
QYUNSLATION_PLAN080_SAMPLE=<源 PDF> QYUNSLATION_PLAN080_OUTPUT=<译文 mono PDF> bash scripts/verify-plan-080.sh
```

## 3. 已知限制（开启前请知情）

- 小标题下划线无法精确到词，只保证不超出所在行。
- 被保留的原文（抬头、名单）保持源文件字体（Arial/Calibri），不统一成宋体。
- 斜体强调在译文中丢失（思源宋体没有斜体）。
- 纯人名（无学位）不做规则判定，仍由模型处理；中译英方向不做保留规则，中文职务与公司名照常翻译。
- 装饰线只处理水平细线；删除线、波浪线、高亮不在范围内。
- 参考文献保留依赖内容形状（卷:页、DOI、et al.、年份），没有这些特征的非标准引文格式可能仍被翻译；`REFERENCE_ENTRIES_CHANGED` 会在开启 QA 后把这类情况报出来。
- 各阈值只在 4 份文档（监管信函、期刊文章、文献、中文登记表）上校准过，误报率样本小。
