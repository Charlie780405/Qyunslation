# PLAN-031 仓库专业治理（派生作品收口）

> 状态：**已完成**（WT-031 已部署）
> 日期：2026-09-08
> 批准记录：用户确认 Cursor 计划「仓库专业治理」后实施
> 关联：PLAN-006a（包名重命名已完成）；不占用 PLAN-030e/f

## 一、背景与目标

Qyunslation 由 [xunbu/docutranslate](https://github.com/xunbu/docutranslate)（MPL-2.0）连同 git 历史导入。PLAN-006a 已把 Python 包/CLI 改为 `qyunslation`，但 GitHub 门面、README、i18n、根目录图标仍呈上游白皮。Contributor 列表是导入历史，不是外邀开发者。

本纲领把仓库按**内部派生作品**收口：Private、保留历史与许可、补 NOTICE、用户可见品牌改为 Qyunslation。

## 二、子计划矩阵

| 编号 | 名称 | 核心职责 | 关键产物 | 前置 |
|---|---|---|---|---|
| **031a** | GitHub 治理 | Private、About、关 Wiki、校正 remote、删 0-ahead 旧分支 | `gh` / remote | — |
| **031b** | 出处与许可 | 保留 LICENSE，新增 NOTICE | `NOTICE.md` | — |
| **031c** | 用户可见品牌 | README/图标/i18n/CLI/页脚/Docker 元数据 | 见 031c | 031b |

## 三、质量不变量

1. **不重写 git 历史**。Contributor 头像保留。
2. **包名仍为 `qyunslation`**，不改 import 路径。
3. **`DOCUTRANSLATE_*` 双读保留**（`QYUNSLATION_*` 优先）。
4. **不改** Caddy / `translate.qyunsgen.com` / 7860 / 8010。
5. **不打断 PLAN-030**；本仓在 `feat/PLAN-031-repo-governance`。

## 四、明确不做

- filter-branch / 新仓重推以「只剩自己」
- 同步上游 DocuTranslate 增量
- 重做 Vue / Gradio UI
- 删除 SPDX / `SPDX-FileCopyrightText: 2025 QinHan`
- 改 PLAN/WT 史实中的「上游 DocuTranslate」字样

## 五、验收

`bash scripts/verify-plan-031.sh` 全绿；根目录第一眼不再是 DocuTranslate 产品名；`NOTICE.md` 与 `LICENSE` 存在。
