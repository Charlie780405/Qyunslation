# WT-030d：PDF 纵向闭环（SSOT 贯通、正文、多栏、表格保护）

> 计划：[PLAN-030d](../plans/PLAN-030-semantic-layout-translation/PLAN-030d-manifest-ssot-execution-parity.md)
> 日期：2026-09-08
> 状态：Tasks 1–10 已完成

本阶段把 `DocumentStructureManifest` 从「产出但无人消费的契约」变成预扫描与执行的共同真相源，并补齐正文、栏式、表格区域与扫描件形态四类语义。两处范围经实测证据后由用户决策修订，均记录在下文而非悄悄让步。

## 一、Checkpoint A：SSOT 地基（Tasks 1–5）

`ManifestStore` 按 `source_sha256` 与 schema 主版本分区持久化，写入走临时文件加 `os.replace` 保证原子性，落盘前先反序列化校验一遍——这一步实际拦下了 `summary` 陈旧的 bug。

实现中撞到两个隐蔽问题：

**摘要陈旧**。执行阶段回写 `execution_status` 后，`summary.status_counts` 仍是扫描时的旧值，`model_validate_json` 直接拒收。补 `DocumentStructureManifest.refresh_summary()`，持久化前重算。

**缓存投毒**。若执行状态直接覆盖结构缓存，下一次预扫描会看到所有对象都已非 `PENDING`，于是报告零可译对象，执行侧也会跳过——同一份文档翻译第二次就什么都不做了。修法是给 `ManifestStore` 加 `kind` 维度，结构清单（`manifest`）与执行审计快照（`execution`）分开存放。

Tier-3 的错误也改为如实上报：加密、缺依赖、单页崩溃各有专属文案与 `ManifestIssue`，不再一律显示「未检测到需要嵌字的插图」。单页失败只记 `SCAN_PAGE_FAILED` 并继续，不再让整份扫描失败。

幻灯样本三方一致：manifest 可译对象数 = `Tier3Result.translatable_count` = 执行区域数 = 12。

## 二、DocLayout 路线判定：不接入

Task 6 启动前对 BabelDOC 0.6.2 的 DocLayout 做了源码调研与本机实测：

| 判据 | 实测 | 结论 |
| --- | --- | --- |
| 权重离线 | `~/.cache/babeldoc/models/*.onnx` 72MB 已缓存 | 不阻塞 |
| 本仓 venv 可导入 | **否**，`babeldoc` 未安装（仅 `onnxruntime` 在） | 需引入 pdf2zh-next 的重依赖 |
| 推理性能 | **1.08s/页**（CPU，`batch_size` 被强制为 1），19 页 20.5s | 超出 Tier-3 的 25s 预算 |
| 栏位 / 阅读顺序 | **不提供**：10 类标签无 column，`ParagraphFinder` 只有字符级 `render_order` | 多栏无论如何都要自研 |
| 表格单元格 | **不提供**：`table_model` 在 0.6.2 被强制置空，RapidOCR 已退役为 no-op | Task 8 不能依赖 |

命中 PLAN §五 的「性能不可接受」回退条件，且它本就不产出 Task 7 需要的栏位信息，故走自研几何路线（`detector="pymupdf_text_blocks"`、`confidence=0.7`），三样本 46 页约 1s。

将来若要接入，最小路径是 `DocLayoutModel.load_onnx().predict(image)`，输入为 72 DPI 渲染图，输出为左上角像素坐标，需自行翻转 y 轴换算到 PDF 点坐标。

## 三、正文、栏式与阅读顺序（Tasks 6–7）

`Canvas.layout_mode` 此前硬编码为 `MIXED`，现按实际版面填充。幻灯先按宽高比短路为 `FREEFORM`，避免自由版面被当成栏式。

原型阶段有个自身的 bug 值得记下：把排序后的 centers 与未排序的 widths 做了 `zip`，对应关系错乱，导致 ljae439 p6、Nature p3/p4 这些明显双栏页被判成单栏。修正后逐页人工核对几何，把 PLAN 里凭估计写的「ljae439 七页、Nature 十三页双栏」更正为实测的 **8 页**与 **18 页**——ljae439 前两页确为全宽标题页与 Plain Language Summary，Nature 末页是全宽作者声明。

**跨栏检测的定义被推翻重来**。原验收写「宽度超过页宽 60% 即记 issue，双栏金样为 0」，但双栏页上的标题、图题、表格标题本来就跨栏，Nature 实测报出 111 个，这条验收自相矛盾。改为全宽元素标 `column="full"` 视为合法排版，只有**窄块越过栏中线**才算异常。最终 ljae439 为 0，Nature 剩 3 个且全在首页摘要区（起排于 37% 的特殊排版）。

正文对象终态为 `EXPLICITLY_SKIPPED` / `delegated_to_babeldoc` / `planned_action="babeldoc_text_layer"`——030d 审计正文但不接管译文生成，不伪装成已处理。

## 四、表格：从「原位重建」降级为「区域保护」

Task 8 原定做单元格级原位重建。探底实测后发现地基不成立，经用户决策降级。

对两个金样的全部带题注表格试过 `find_tables()` 三种策略：

| 位置 | 题注 | `lines_strict` | `lines` | `text` |
| --- | --- | --- | --- | --- |
| ljae439 p5 | Table 1、2 | 0 | 0 | 整页 77×10 |
| ljae439 p7 | Table 3 | 0 | 0 | 整页 46×15 |
| Nature p4 | Table 1 | 0 | 1（29×2，列数错） | 整页 95×10 |
| Nature p5 | Table 2 | 0 | 0 | 整页 100×13 |
| Nature p9 | Table 3 | 1（35×3） | — | — |

六个真表格召回 2 个，其中一个列数还是错的。同时在**无表格**的图表页大量假阳性：Nature p7 测出 6×10 全空表，p10 测出六个 2×7。

`strategy="text"` 看似召回率高，实为按空白间隙暴力切列：bbox 覆盖整页，正文段落被吞入，且文字被拦腰切断——实测出现 `Reduce|d dosing`、`tralokinu|mab`、`Age (years), mean ` + `D)`。这种切法足以破坏 `44.1 (22.1)` 这类数值，与「数字逐 token 与原文一致」的红线直接冲突。根因是这批临床期刊用的是**无竖线的学术三线表**。

降级后的做法是从表题注锚点出发、按横线群圈定区域（`qyunslation/structure/tables.py`）：

- 横线按 y 容差 1.5pt 合并，顶线常被切成多段（ljae439 p5 切成三段）
- 相邻横线间距超过页高 20% 即断开，用于甩掉页脚线。该阈值下界受 ljae439 p5 约束（表头线 0.148 到底线 0.287 相隔 0.139），上界受 Nature p5 约束（表格底 0.661 到页脚线 0.954 相隔 0.293）
- 无表题注的页不产生任何区域，这是零假阳性的关键

结果：六个表格全部圈定、假阳性 0。表格区域并入正文过滤后，Nature p5 的 `BODY` 泄漏由 **27 降至 7**（剩余为该页表格之外的真实双栏正文），`TABLE_GEOMETRY_MISSING` 消失。`TableObject` 挂 `detector="table_rule_lines"` 证据并带 `reconstructed=False`，`planned_action` 仍为 `text_layer`，如实标注未做单元格重建。

单元格级重建移出 030d，需另做技术选型（`pymupdf4llm` / `camelot` / 深度学习表格模型均未安装，离线可用性与精度都待验证）。

## 五、原生 / 扫描 / 混合逐页判定（Task 9）

`hpd_ocr.pdf_needs_hpd` 按整档字符数（< 80）一刀切，部分页扫描的混合件会被漏判。测试里锁定了这个盲区：合成夹具（两页原生 + 一页扫描）整档字符数 ≥ 80，整档门槛判「不需要 OCR」，逐页判定则正确识别出第三页需要。

判定口径：页面字符数 < 20 即 `SCANNED`（无文字层必须走 OCR，宁可多判不可漏判）；有文字层且单图覆盖 ≥ 60% 为 `HYBRID`（OCR 产物）；其余 `NATIVE_TEXT`。覆盖阈值有明确实测间隔：

| 样本 | 最大单图覆盖 | 判定 |
| --- | --- | --- |
| FDA PIND（原始扫描件，20 页） | 0.75 | SCANNED |
| FDA PIND（HPD OCR 后） | 0.75 + 文字层 | HYBRID |
| Abstract（24 页扫描件） | 1.00 | SCANNED |
| ljae439 | 0.22 | NATIVE_TEXT |
| Nature | 0.00 | NATIVE_TEXT |

**性能坑**：首版用 `get_image_rects()` 量覆盖，FDA PIND 20 页要 **17.5s**，几乎吃掉 Tier-3 的 25s 预算。该函数需按 xref 反查内容流。改走 `get_text("dict")` 的图像块 bbox 后降到 **0.4s**（快约 125 倍），判定结果完全一致。

HPD 血缘按实际能力落地：扫描阶段 OCR 尚未发生，无法记录已完成的转换血缘，改为记 `ManifestIssue(code="PAGES_REQUIRE_OCR")` 列出需要 OCR 的页号。

## 六、验收与部署

单命令门：

```bash
bash scripts/verify-plan-030d.sh
```

门内覆盖模块编译、八个聚焦测试文件、金样断言（语义计数、正文与阅读顺序、表格区域、形态记录）、FDA PIND 预算断言、结构套件 XFAIL 清单，以及 028 / 029 / 030c 三个既有门。

顺带修了 030c 门的一处退化：它的默认超时是 300s，而结构套件已增长到 500s 量级，`timeout --signal=INT` 发出的 SIGINT 会表现为 `KeyboardInterrupt` 并被记成「structure suite failed」。两个门的默认超时统一提到 900s。

部署（本阶段改动均在扫描与预扫描侧，不涉及 GUI 补丁）：

```bash
systemctl --user restart qyunslation-office.service pdf2zh.service
curl -s -o /dev/null -w '%{http_code}\n' https://translate.qyunsgen.com/
```

## 七、遗留

- **表格单元格重建**未做，需技术选型后单独立项。当前只保护不重建，`reconstructed=False` 已如实标注。
- **首页摘要跨栏** 3 例（Nature p1）保留为 `LAYOUT_COLUMN_OVERFLOW` 警告，反映首页起排于 37% 的特殊排版，非缺陷。
- **合成夹具 `double-column.pdf`** 每栏仅一行 37 字符且两行同 y，PyMuPDF 会合并成单块，几何上不构成双栏，因此未用于栏检测验收；该夹具是 030a 的格式检测契约基线，改动会波及 `catalog.v1.json` SHA 校验。
- `QY030-PPT-001`（PPTX 图片对象）仍为唯一 XFAIL，留待 030g。

## 八、契约字段空置登记（PLAN-030e 收拢）

详见 [`WT-030e-docx-vertical-closure.md`](./WT-030e-docx-vertical-closure.md) §四。030e 已贯通 `translatable_blocks`（部分）、`output_evidence`（执行 checks）与 DOCX 表格行列数；PDF 表格行列、fast_fingerprint 等仍预留。
