# PLAN-030e-residual 子计划：030e 已知局限收口

**状态**：待批准  
**类型**：030e 遗留修复（非新格式闭环）  
**依赖**：PLAN-030e 已完成  
**建议顺序**：**先于 PLAN-030f 批准门执行**（体量小、解除 030f/030g 环境阻塞）  
**验收门**：`bash scripts/verify-plan-030e-residual.sh`（待建）

## 一、背景

PLAN-030e 主交付已完成，但 [WT-030e](../../walkthroughs/WT-030e-docx-vertical-closure.md) §五 与契约登记仍留有三类**应在下一格式闭环前收口**的局限。本计划不扩展 030e 范围，只把已登记项变成可验收的关闭项。

## 二、范围

| ID | 局限 | 根因 | 本计划交付 |
| --- | --- | --- | --- |
| R1 | 生产无 LibreOffice，`.doc`/`.ppt` 规范化 HTTP 503 | 脚本已写、未 sudo 安装 | 生产安装 + `OFFICE_CONVERTER`/`SLIDE_RENDERER` 探针转绿 + 集成测试不再 skip |
| R2 | 多节 DOCX 正文全挂 `section:1` | `docx_walk` 未按 `sectPr` 断点切段 | walk 层识别分节符；`scan_docx` 按节分配 `canvas_id`；夹具断言第二节 BODY |
| R3 | verify 门对仓外样本仅 BLOCKED | 用户选择不入库真实业务 PDF | **不**入库临床/监管样本；补合成幻灯/扫描等价夹具，使 15 项验收在无 `QYUNSLATION_SAMPLE_ROOT` 时仍可跑（BLOCKED 降为 INFO） |

### 明确不纳入

- PDF 三线表单元格重建 → [PLAN-030-table-pdf-cell-reconstruction](./PLAN-030-table-pdf-cell-reconstruction.md)
- PPTX 嵌图 `QY030-PPT-001` → PLAN-030g
- 契约预留字段（`fast_fingerprint` 等）→ PLAN-030h/030i
- 像素级视觉 diff → 不做

## 三、任务

### Task 1：LibreOffice 生产就绪（R1）

1. 在生产机执行 [`scripts/install-libreoffice.sh`](../../../scripts/install-libreoffice.sh)（需 sudo）。
2. `probe_runtime_capabilities()` 中 `OFFICE_CONVERTER`、`SLIDE_RENDERER` 为 available。
3. `test_real_libreoffice_converts_doc_fixture_to_docx` 在 CI/生产探针环境为 **必跑**（非 skip）。
4. WT 记录：转换器版本、`soffice` 路径、一次 legacy `.doc` 端到端 smoke。

**完成定义**：上传 `.doc` 得 DOCX 规范化产物，不再 503。

### Task 2：DOCX 多节 canvas 归因（R2）

1. `docx_walk.py`：遍历 `w:body` 时跟踪当前 `section_index`（遇 `w:sectPr` / python-docx `add_section` 断点递增）。
2. `container_ref` 形如 `section:2/body`；页眉页脚已有 `section:N/header.*`。
3. `scan_docx.py`：`canvas_id = f"section:{index}"` 与 `extract_canvases` 产出一致。
4. 扩展 `review.docx` 或 truth：第二节至少 1 个 BODY；`test_scan_docx.py` 断言对象 `canvas_id` 分布。

**完成定义**：双节夹具上 BODY 不全部落在 `section:1`。

### Task 3：仓外样本合成等价（R3）

1. 新增合成夹具（不含真实业务数据）：
   - **slide-equivalent.pdf**：12 个无题注可译区（模拟 QX027N 幻灯 prescan=execution=12）。
   - **scanned-equivalent.pdf** + **.hpd-ocr.pdf**：20 页扫描态 + OCR 后 HYBRID（模拟 FDA PIND 预算与形态断言）。
2. 测试优先用合成路径；`QYUNSLATION_SAMPLE_ROOT` 存在时仍跑真实样本作加强回归。
3. `verify-plan-030d.sh` / `030e.sh`：无仓外文件时跑合成基线；缺失时 BLOCKED 仅针对「加强回归未跑」，不阻断主门。

**完成定义**：换机无 `/home/dev/pdf2zh/...` 时，030d 核心断言仍全绿。

## 四、验收

```bash
bash scripts/verify-plan-030e-residual.sh   # 待建：Task 1–3 + 030e 门回归
```

质量红线：030e/030d/030c/028/029 门不退化；`QY030-PPT-001` 仍为唯一 xfail。

## 五、风险与回滚

| 风险 | 缓解 |
| --- | --- |
| LibreOffice headless 占内存 | 仅规范化路径调用；超时与 030b 一致 |
| 合成夹具与真实幻灯行为漂移 | 真实样本路径保留为 optional strengthened |
| 分节 walk 漏掉连续分节符 | 以 `review.docx` + 手工双节 DOCX 双断言 |

Task 1 可独立回滚（卸载 LibreOffice）；Task 2/3 仅影响 DOCX 扫描与测试路径。
