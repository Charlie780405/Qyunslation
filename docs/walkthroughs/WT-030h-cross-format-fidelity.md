# WT-030h 跨格式版式保真与入口一致性

> 计划：[PLAN-030h](../plans/PLAN-030-semantic-layout-translation/PLAN-030h-cross-format-fidelity.md)
> 日期：2026-09-08
> 验收门：`bash scripts/verify-plan-030h.sh` → `SUMMARY: PASS fail=0`

## 一句话

把验收基线从会被回收的运行时目录搬进仓内，把 GUI 入口的七处手写扩展名收敛到能力矩阵，并用同内容四承载物与四份版式金样把「契约声明了但没人验」的部分逐条查清。

## 做了什么

### H1 验收不再依赖运行时样本目录

原先 `verify-plan-030d/030e` 和多个结构测试锚定 `/home/dev/pdf2zh/pdf2zh_files/<uuid>/`。那是 pdf2zh 的会话目录，会随会话回收，换机必缺；缺失时门只报 skip，「全绿」并不代表验过。

新增三份合成等价夹具（20 页扫描件、其 OCR 后的 HYBRID 形态、16:9 无题注幻灯 12 区），主门断言走仓内合成件，外部真实金样降级为加强回归。`conftest.py` 提供 `scanned_pdf` / `ocr_pdf` / `slide_pdf` 间接夹具做双轨参数化。

造合成幻灯件时踩了两个坑，都记在这里以免重蹈：文字太短会被判成 `SCANNED` 而非 `NATIVE_TEXT`（要过 `MIN_PAGE_CHARS`）；矩形间距 24pt 时 PyMuPDF 会把绘图命令合并导致检出 0 个矢量区，收紧到 20pt 后聚类才认。

顺带修掉 `verify-plan-028.sh` 一个真 bug：设了 `QYUNSLATION_SAMPLE_ROOT` 却在其中找不到样本时，它返回一个不存在的路径直接 BLOCKED——而那份 `nature_comm_53384.pdf` 本来就在仓内。

### H2 GUI 入口格式统一到能力矩阵

`capabilities.py` 早已把 WebP/BMP/TIFF 登记为 `CORE`，但生产 GUI 的文件选择器选不到它们——扩展名在七处各写各的。现由 `gui_extension_manifest()` 统一导出，`scripts/_gui_extensions.py` 在打补丁时渲染字面量（注入代码运行在 pdf2zh 进程，那里没有 `qyunslation` 包）。清单载入失败直接 `SystemExit`，宁可服务起不来也不用过期字面量打补丁。

`file_types` 顺带补齐大写变体：历史补丁只手工加了 `.PDF`，`.DOCX` 等一律选不中。

### H3 跨格式语义对账

四份承载同一内容的夹具。结论：PDF 与 DOCX 的编号语义身份**逐项相等**；正文分段数差异由承载粒度解释；PPTX 的 `semantic_id` 带幻灯片坐标且题注以 `TEXT_BOX` 承载；PNG 压平成单个 `IMAGE`。

### H4 版式金样

新增三栏、四栏、逐页混合栏、A0 海报四份金样，暴露出四处判定缺口（见下）。

夹具改用 `insert_textbox`：裸内容流里同一行的多段文字会被 PyMuPDF 合并成一个横跨整页的块，栏式判定看到的 narrow 块数不足——最初的双栏合成件就是因此一直被判成 SINGLE 而无人察觉。

## 部署与线上验证

补丁链由 `pdf2zh.service` 的 `ExecStartPre` 驱动，重启即重打。重启前备份了 `gui.py`。

第一次重启失败：`preview-url` 自检报 `image preview not switched to file url`。根因是 `office-preview` 的幂等判定只看 marker，marker 已存在就跳过整段注入，集合永远停在旧值，下游 `preview-url` 的锚点因此对不上。补 `refresh_extension_sets()` 就地升级已注入的集合后，完整重启干净通过。同类自愈也加进了 `office-route` 的 `needs_refresh` 条件。

线上确认：

- `pdf2zh.service` 与 `qyunslation-office.service` 均 `active`，重启日志无 ERROR。
- 已安装 GUI 的 `_QY_OFFICE_SIDECAR_EXT` 与清单逐字节一致（契约测试断言）。
- 五种 CORE 图片格式过 sidecar `image-probe` 全部受理，TIFF 此前返回 `unsupported_format:.tiff`。返回的 `skip/too_small` 是尺寸策略，不是格式拒绝。

## 验收记录

`bash scripts/verify-plan-030h.sh` 九项全 PASS：模块编译、清单在补丁运行时可载入、GUI 清单契约、跨格式对账、版式金样、夹具可复现且与 catalog 一致、**无运行时样本目录时结构套件仍全绿**、sidecar 受理全部 CORE 图片格式、已安装 GUI 与清单一致。

结构套件 344 passed。`verify-plan-028.sh` 在 `SAMPLE_ROOT` 指向空目录时 PASS（blocked=0）。

## 留下的债

修这五条都要动判定逻辑核心，会牵动 `profiles.py` 的版式策略与 nature 双栏样本的既有断言，须另立子计划。现状已被断言锁住，修好时断言会转红提醒摘除。

| # | 债 | 后果 |
| --- | --- | --- |
| D1 | 三栏、四栏一律判 `DOUBLE`，`LayoutMode.MULTI` 是死枚举 | 契约声明支持 MULTI，实现无从表达栏数 |
| D2 | 三栏页中间栏压在中线上被归入左栏 | 阅读顺序在扫描阶段就错乱，后续排版补不回来 |
| D3 | 正文块少于 3 的双栏页短路成 `SINGLE` | 短文、附录、表格页丢栏 |
| D4 | A0 海报宽高比 1.41 够不着 `SLIDE_ASPECT=1.55` | 九块分区被当成期刊双栏串接，`POSTER_SECTION` 在 PDF 通道未被识别 |
| D5 | `content_profile` 由扫描器按格式硬编码 | 同一内容换容器就换 profile |

D4 影响面最大：海报是 030f 的一等场景，PDF 通道上的海报目前完全走错分支。建议下一个子计划先修 D4，再一并处理 D1–D3。

## 回滚

- 代码：`git revert` 三个提交（H1+H2、H3、H4）。
- 生产 GUI：`gui.py` 备份在 `/home/dev/pdf2zh/gui.py.bak-plan030h-20260908T134058Z`；恢复后需同步回退补丁脚本，否则下次重启会再打一遍。
