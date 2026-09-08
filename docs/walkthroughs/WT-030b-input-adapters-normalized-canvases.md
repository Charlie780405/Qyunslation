# WT-030b：输入适配与归一化画布实施记录

> 状态：**完成**
> 日期：2026-09-07
> 对应计划：[PLAN-030b](../plans/PLAN-030-semantic-layout-translation/PLAN-030b-input-adapters-normalized-canvases.md)

## 一、交付结果

PLAN-030b 已把 PDF、DOCX、核心图片和 PPTX 接入同一条 fail-closed 输入准备链路：

- 文件名、声明 MIME、魔数和 OOXML 关键 part 联合判定，未知内容不再回退 TXT；
- PDF page、DOCX section、图片 frame、PPTX slide 均形成 canonical canvas；
- DOC/PPT 通过隔离 LibreOffice 适配器规范化到 DOCX/PPTX，并记录源/目标 hash、资产与转换血缘；
- 自动工作流使用规范化后的格式，手动工作流与真实格式冲突时在任务创建前失败；
- 两个主上传端点和图片扩展端点分块读取，默认上限 256 MiB，可用
  `QYUNSLATION_MAX_UPLOAD_BYTES` 调整；
- 任务状态只保存格式、hash、能力、画布数量和血缘，不保存原始字节或正文；
- 原有日志中的 MinerU token 前缀输出已移除。

本阶段只建立输入与空语义画布，不把物理位图/矢量区域解释为 Figure/Table，也不实现图片翻译回写。

## 二、真实样本

知识库样本已物化到 `tests/fixtures/structure/reference/ljae439.pdf`，仅用于开发测试：

- SHA-256：`8e9893b21e6aab4a057ba730eba40f6a9bd696f3538ed05ffc3fc5eb8470f10c`
- 大小：1,871,751 bytes
- 探测格式：PDF
- canonical canvas：10 个 PAGE，编号 `page:1`–`page:10`
- 页面尺寸：约 595.276 × 782.362 pt
- 语义真值继续固定为 Figure 1–5、Table 1–3，但归并实现归属 PLAN-030c

生产包扫描测试证明 `qyunslation/**/*.py` 不含该文件名、知识库 locator 或本机附件路径；真实运行仍处理用户上传的任意受支持资料。

## 三、验证证据

`bash scripts/verify-plan-030b.sh` 的最终结果：

```text
PASS: PLAN-030b modules compile
PASS: focused input, normalization, canvas, prescan, and entry tests
EXPECTED_RED: only PLAN-030c semantic count and PLAN-030g PPT image execution remain XFAIL
EXPECTED_RED: --runxfail proves the exact two downstream gaps still fail
PASS: ljae439 TEST_FIXTURE_ONLY bytes, SHA-256, and ten canvases
PASS: full pytest regression excluding recorded archive failures
EXPECTED_RED: three unchanged pre-PLAN-030 archive naming failures
SUMMARY: PASS expected_red=3 blocked=0 fail=0
```

结构测试单独运行结果为 `129 passed, 2 xfailed`。四个归属 030b 的严格红灯已经转为普通绿测；保留的两项分别属于：

1. `QY030-SEM-001` / PLAN-030c：物理区域尚未按语义 Figure 编号归并；
2. `QY030-PPT-001` / PLAN-030g：PPTX picture shape 尚未成为可翻译图片对象。

全仓测试排除 `tests/test_pdf2zh_archive.py` 后通过；该文件中的 3 个实施前既有 archive 命名失败保持精确不变。

## 四、运行能力实测

当前开发环境可用：PyMuPDF、DOCX/PPTX OOXML、Pillow、TIFF、GIF、AVIF、RapidOCR/ONNX Runtime 和 fontconfig。

当前开发环境未安装 LibreOffice/soffice，也没有 CairoSVG、HEIF codec 或 slide renderer。因此：

- DOC/PPT 上传会在任务创建前明确返回运行能力不可用，而不会误入 DOCX/PPTX 工作流；
- 转换器成功、失败、超时、缺输出和错误输出格式均由注入式测试覆盖；
- SVG、HEIF/HEIC 等条件格式按能力探针显式接受或拒绝，不宣称当前环境可执行。

## 五、提交与回滚

实施提交按可回滚增量拆分：

1. `114ac45` 输入格式安全探测；
2. `eae24e7` 运行能力探针；
3. `8f56ea8` canonical canvas adapters；
4. `36d4667` legacy Office 规范化；
5. `e087703` PreparedDocument 与血缘；
6. `c24434c` 共享预扫描路由；
7. `f09191f` 生产上传入口；
8. `e25dc2c` 真实样本与验收门。

若需回滚生产行为，优先回滚 `f09191f`；输入内核、测试和样本可独立保留。不得恢复“未知格式→TXT”或“.ppt 直接进入 PPTX”两个旧行为。

## 六、下一阶段边界

PLAN-030c 应消费本阶段生成的画布、hash 和 source references，建立统一语义扫描：按题注与编号把位图、矢量和多次 occurrence 归并为 Figure 1–5，并独立产出 Table 1–3。开始实现前仍需先形成详细子计划并取得用户批准。
