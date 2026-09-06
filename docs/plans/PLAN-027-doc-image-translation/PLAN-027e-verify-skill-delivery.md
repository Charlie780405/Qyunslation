# PLAN-027e 子计划：自动化验收、Skill 沉淀与发布交付

## 一、目标与解决痛点

1. **解决痛点 1（测试流于形式与伪假绿）**：
   - 审查指出的严重漏洞：之前的测试仅断言“blob 发生改变”或“文件大小改变”，无法区分是真的成功翻译还是整图被涂黑破坏。
2. **解决痛点 2（技能资产未沉淀）**：
   - 解决内嵌图翻译、共享解耦、Alpha 透明度保真的工程经验如果不形成标准规则，后续开发者容易再次犯相同低级错误。

---

## 二、详细验收脚本设计（`scripts/verify-plan-027.sh`）

验收套件必须包含 **6 个维度的硬性自动化断言**，不允许因缺失测试样本而直接跳过核心逻辑：

### 1. 静态与代码结构断言
- 断言新增的核心模块与接口全部存在：
  - `doc_image_policy.py` 中的 `evaluate_image_candidate`、`_filter_translatable_blocks`；
  - `custom_api.py` 中的 `/service/image-probe` 路由；
  - `pdf_figure_crop.py` 中的 `find_safe_vector_figures`；
  - `pdf_image_translate.py` 中的 `translate_pdf_images`；
- 幂等性断言：`apply-pdf2zh-prescan.py` 与 `apply-pdf2zh-docimg.py` 连续执行两次，产物 diff 必须绝对为空；
- 服务编排断言：`scripts/pdf2zh.service` 完整包含新补丁的 ExecStartPre 配置。

### 2. 策略与探针单元测试
- 编写独立的测试用例：
  - 30×30pt 图标、纯色背景图被 `doc_image_policy` 拒收；
  - 300×200pt 临床流程图被准确接收；
  - 纯坐标轴图（只含数字 0, 10, 20）被判定为 `translatable_blocks: 0`；
  - 中译英任务下，原本就是纯英文的代码图被判定为 `already_target_lang` 跳过；
  - 模拟透明 PNG 经过嵌字流程，像素透明度蒙版无损恢复。

### 3. DOCX 端到端集成测试
- 通过 `python-docx` 现场在临时目录生成一份测试 DOCX：
  - 页眉放置一个小 Logo，正文放置一个 400×250pt 的临床试验设计流程图，两者共享同一底层 ImagePart；
  - 运行 `DocxTranslator._overlay_embedded_images`；
  - **断言**：正文图内文字被成功翻译为目标语言；页眉 Logo 的 ImagePart 被自动克隆解耦，Logo 的 MD5、像素内容和显示尺寸 100% 保持未修改状态；
  - **断言**：成功生成 `<stem>.imgtr.json` 清单文件，且记录包含各项详细审计信息。

### 4. PDF 端到端集成测试
- **策略 A（位图解耦）**：
  - 通过 PyMuPDF 现场生成 2 页 PDF，两页引用同一个位图 xref；
  - 执行 `translate_pdf_images`；
  - **断言**：仅正文页图片被更新，另一页图片内容完全不受影响；更新后图片物理尺寸与原图绝对一致。
- **策略 B（矢量图防覆盖）**：
  - 生成包含可选中正文段落与下方带文字矢量边框图的 PDF；
  - **断言**：矢量区域被安全覆盖，但上方正文段落文字层 100% 保留（调用 `page.get_text()` 依然能完好提取出正文文字）。
- **整页扫描图守卫**：
  - 构造一张占页面积 95% 的大图，断言两条策略均跳过，未破坏整页底图。

### 5. 代际锁防竞态模拟测试
- 模拟前端上传文件 A 触发 Tier-2 探针，在探针延时期间立即传入新代际 token 并上传文件 B；
- 断言文件 A 返回的数据被主动丢弃，未污染当前文件 B 的 UI 状态字典。

### 6. PLAN-026 视觉回归测试
- 必须连带执行 `scripts/verify-plan-026.sh`，确保独立单图嵌字、括号线保护、字号层级与 C1~C10 QC 0 回归。

---

## 三、Skill 沉淀规范（SK-Q002 扩充）

在 `.cursor/skills/image-overlay-translation/SKILL.md` 中新增专章：**《文档内嵌图原位翻译与安全覆盖工程规范》**：
1. **共享资源解耦铁律**：DOCX 与 PDF 中遇到跨容器或多处复用图片时，一律执行“先克隆新资源对象、重定向局部引用、再单点修改”，严禁盲目全局覆写。
2. **透明通道双通道保护**：底图 OCR/Inpaint 与前景文字渲染分离，始终保留原始 Alpha/SMask 蒙版通道。
3. **矢量覆盖正文安全门禁**：对 PDF 页面中未分离矢量，若与正文重叠 >10% 或面积 >80%，坚决执行 Fail-Closed 熔断，绝不允许整页降级为位图。
4. **两段式预扫描与代际防线**：前端异步预扫描必须挂载唯一的代际令牌，禁止使用非隔离的全局布尔变量。

同步更新 `pitfalls.md`（记录共享 Part 污染、Alpha 丢失、矢量整页误判案例）、`reference.md`（记录各尺寸门槛与环境变量默认值）以及 `registry.md`。

---

## 四、生产发布与回滚预案

1. **精确提交与合并**：
   - 切换到 feature 分支开发，遵循无 emoji、HEREDOC 规范撰写提交信息；
   - 通过 `--no-ff` 合并入 `main`。
2. **推送双远程**：
   - 同步推送到 `origin`（gitea）与 `mirror`（github）。
3. **服务平滑热启**：
   - `sudo systemctl restart qyunslation-office.service`
   - `sudo systemctl restart pdf2zh.service`
4. **生成 WT 报告**：
   - 编写 `docs/walkthroughs/WT-027-doc-image-translation.md` 并回填部署 commit hash。
