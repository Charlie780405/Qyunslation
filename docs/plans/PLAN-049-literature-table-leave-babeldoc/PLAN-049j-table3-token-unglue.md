# PLAN-049j：表3 粘连切分与七列收口

> 状态：已实现
> 父计划：[PLAN-049](./PLAN-049-literature-table-leave-babeldoc.md)

## 根因

| 症状 | 机制 |
| --- | --- |
| `90.0111` / `20.422` | `split_cells` 的 `\d+(?:\.\d+)?` 贪心吃后续小数 |
| 第二行只剩 `Q2W` | flowing 舀 token 错切后耗尽 blob |
| 表头无 IGA/EASI | `n_cols==6` 不强制七槽；孤立 `A`/`a` 入槽 |
| `Q4WS`+`afetyFU` | pretreat 不拆 `Q4WSafety` |

## 交付

1. 按 origin 格形态（int/dec1/dec2/visit/pn/dose）从 dest 段头剥 token
2. pretreat：`Q[24]W`+字母/汉字/`<` 必拆；`90.0`+`1`+`11.2` 粘连 `90.0111.2`→`90.0 1 11.2`
3. `n_cols>=6` 强制七槽；丢掉孤立 `A`/`a`
4. origin 有满格而 dest 空时从 remaining blob 补写

## 判据

- `split_cells("Q2W第52周40阴性90.0111.2")` → 七 token 含 `90.0` `1` `11.2`
- 回放 ffc3 mono 表3：无三位小数粘连 token；Visit 一列；EASI 独立 x
