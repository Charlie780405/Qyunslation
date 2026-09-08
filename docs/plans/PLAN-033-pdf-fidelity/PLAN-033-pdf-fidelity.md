# PLAN-033：学术 PDF 图表识别与原文不可变

> 状态：**纲领已修订；033a / 033c 已完成（未合 main）**
> 日期：2026-09-09
> 基线：`775d0c1`（PLAN-030h）
> 原作者：Codex（2026-09-09 递交）
> 修订：对照仓库实现后收口范围
> 验收门：各子计划独立 `scripts/verify-plan-033a.sh` …；总门 `scripts/verify-plan-033.sh` 禁止嵌套 028–030h 全门
> 分支：`codex/plan-033-pdf-fidelity`（已从 main 派生）

## 一句话

先让题注计数正确，再切断「先嵌图翻译再喂 BabelDOC」这条污染原文半边的链路。其它条目按风险单独立项，不在本纲领里一次做完。

## Codex 原稿的问题（修订依据）

对照 `captions.py`、`manifest_store.py`、`doc_image_prescan.py`、PLAN-030h D1–D5 之后，原稿把六件事捆成一个计划，其中一半已经有实现或已被登记为别的债：

| 原稿条目 | 仓库现状 | 修订 |
| --- | --- | --- |
| 算法版本写入 cache key | `ManifestStore.get_current()` 已按 `producer.name/version` 失效；截断结果已不入库 | 只把 `PDF_STRUCTURE_SCANNER_VERSION` 从 `1.1.0` 升到 `1.2.0`，不另造版本体系 |
| caption 丢空格 | **真缺口**。`caption_anchors` 对 span 做 `"".join()`，ScienceDirect 样本拼成 `Table 2Response...` | **033a 必做** |
| Manifest 数据模型大改 | 角色、bbox、来源、执行态已在 `models.py` | 不扩模型；计数仍走唯一 `semantic_id` |
| 自研表格提取器、弃用 RapidOCR adapter | `tables.py` 已有词块/线段提取；adapter 空实现是 BabelDOC 侧兼容层 | **033b 仅在 033a 之后仍缺几何时补**，禁止为「不调用空实现」重写提取器 |
| 先 `.imgtr.pdf` 再 BabelDOC | **真缺口**。`apply-pdf2zh-docimg.py` 把嵌图译文当 BabelDOC 输入 | **033c 必做** |
| 全格式兼容 | 030a–030g 已闭环；本缺陷是 PDF 链路 | 不扩到 DOCX/PPT/图片 |
| 参考文献零翻译 | 未证明是本样本主痛点；全文禁译参考文献会误伤正文引用句 | **033d 另立**，本纲领只登记 |
| 三栏/海报栏式 | 即 030h **D1–D5**，金样已锁现状 | **不并入 033**。本样本是 11 页单栏综述，不依赖 MULTI |
| 300 DPI 懒加载预览 | GUI 补丁，与扫描无关 | **033e 另立** |
| 11 页金标入库 | Elsevier PDF，版权不可进 git；且在 `pdf2zh_files/<uuid>/`，会话回收即消失（030h 刚修过这类脆弱性） | 仓内用**合成夹具**复现 span 拼接；外部 PDF 仅作可选加强回归 |

首要样本已定位（**不入库**）：

- 路径（本机会话）：`/home/dev/pdf2zh/pdf2zh_files/d10bbff3-0701-431b-ad9e-9992f4f7792c/1-s2.0-S2666636725013958-main.pdf`
- 副本：`/home/dev/.hermes/attachments/1-s2.0-S2666636725013958-main.pdf`
- 11 页，SHA-256 `c88ea994746e13904ed012943130896426b8812f939ae14917e1c48f59b2f8dc`
- 基线扫描：Figure `[1, 2]`，Table `[1]`；p6/p7 题注块存在但 `table_caption_num` 为 None

## 目标

关闭两条用户可感知的缺陷：

1. **计数**：同一语义对象不因 span 无空格而失踪。11 页样本（若在场）必须 Figure=2、Table=4；仓内合成件必须检出 `Table 2/3/4`。
2. **原文不可变**：BabelDOC 的输入永远是原始上传 PDF 的字节；双语左侧与原稿逐页一致。

## Out of Scope

- 030h D1–D5（三栏/海报/`content_profile` 硬编码）
- 自研 Camelot 级表格重建、引入 Java/Camelot
- 把 Elsevier PDF 提交进仓库
- 300 DPI 预览重做（033e）
- 参考文献区禁译（033d）
- 字体一致性像素回归、视觉金样批准（Checkpoint D）
- 改 `glossaries/auto-proper-nouns.csv`

## 子计划

### 033a：题注空格与计数契约（已完成）

见 [PLAN-033a](./PLAN-033a-caption-count.md)。

- span/行拼接保留词界空格；`see Table 4` 仍不计对象。
- 合成夹具复现 `Table 2` + `Response...`。
- 扫描器版本 `1.2.0`，旧缓存自动失效。
- 外部 11 页 PDF 在场则断言 Figure=2/Table=4，缺席 skip。

### 033c：原文不可变流水线（已完成）

- 保留 `_pre_imgtr_origin_path`；BabelDOC / HPD 只吃原稿。
- 嵌图/表格后处理发生在**单语译文**和**双语右侧**，禁止写回作为 BabelDOC 输入的文件。
- 回归：同一 PDF 双语左侧页面渲染 hash 与原稿一致。

### 033b：表格几何补强（仅当 033a 后仍有 `TABLE_GEOMETRY_MISSING`）

- 在现有 `tables.py` 上补间隙/OCR 回退，不换库。
- 验收：四个表都有可译区域或显式 WARNING，不得静默漏译。

### 033d / 033e（登记，本纲领不施工）

- 033d：参考文献标题可译、条目正文保留；与术语采集互斥。
- 033e：当前页 300 DPI 懒加载；进度条用语义对象数，不用内部 OCR 步数。

### 033f：门禁

- `verify-plan-033.sh` 只跑 033 自己的测试 + 结构套件一遍。
- 禁止把 028/029/030 全门嵌进来。

## 风险

| 风险 | 缓解 |
| --- | --- |
| 给所有 span 插空格会拆开 `Fig.` / `1,234` | 只在「前一段以字母数字结尾、后一段不以空白/标点开头」时插空格 |
| 外部 PDF 消失后计数无回归 | 合成夹具是主门；外部是加强回归 |
| 033c 改补丁链让服务起不来 | 改前备份 `gui.py`；补丁自检失败不得启动 |
| 误把 D1–D5 和预览塞进本批 | Out of Scope 写死 |

## 交付约定

- 原子提交顺序：文档修订 → 033a 代码+测试+verify →（另批）033c。
- 精确 `git add <路径>`。
- PDF 样本只用于本机；本计划不增加下载或分发。
