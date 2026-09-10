---
name: settings-inline-left
overview: 把设置页中真正有用的配置搬到翻译页左栏（文档类型模板常驻 + 高级选项折叠面板），填补左下空白；取消 ⚙️ 独立入口，其余控件永久隐藏但保留为参数载体，避免打乱 build_ui_inputs 的位置映射。
todos:
  - id: plan-doc
    content: 写 docs/plans/PLAN-016-settings-inline/PLAN-016-settings-inline.md 纲领
    status: completed
  - id: patch-script
    content: 新增 scripts/apply-pdf2zh-settings-inline.py：搬迁 doc_profile/page_range/page_input/only_include_translated_page/glossary_file/ignore_cache/watermark_output_mode/lang_selector/save_btn 定义到左栏，原位置留占位注释
    status: completed
  - id: docprofile-change
    content: 补 doc_profile_dropdown.change 绑定，修手动选模板不写 state 的 bug
    status: completed
  - id: hide-entry
    content: sidebar 两个 tab 按钮 visible=False + CSS 收回 sidebar-nav 空列与 settings-container
    status: completed
  - id: css-adv
    content: 高级选项 Accordion 样式，保证左栏 flex 与一屏不滚动不被破坏
    status: completed
  - id: service-wire
    content: pdf2zh.service 追加 ExecStartPre（置于 office-preview 之后）
    status: completed
  - id: verify
    content: scripts/verify-plan-016.sh 断言 + ast 语法校验 + 浏览器核对 + WT-016 文档
    status: completed
  - id: ship
    content: feat 分支精确 commit → no-ff merge main → 推远程 → 重启 pdf2zh → WT 验收
    status: completed
isProject: false
---

# PLAN-016 设置项内联左栏与配置入口收敛

## 硬约束（决定实现方式）

[gui.py:941-1014](/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py) 的 `build_ui_inputs(*args)` 按**位置**映射 `fixed_param_names`，[gui.py:7828](/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py) 的 `ui_setting_controls` 是变量名列表。因此：

- **可以**把控件的**定义位置**从设置页搬到左栏（变量名不变，列表和位置映射完全不受影响）。
- **不可以**删除任何控件，删一个后面全部参数错位。"取消"一律做成 `visible=False`，值继续由 `config.toml` 提供。

## 选项必要性分析（分类结论）

- **被文档模板强制覆盖，UI 值 100% 无效** —— `doc_profile.apply()` 每次翻译开头直接改 settings（[doc_profile.py:104-124](/home/dev/qyunslation/scripts/doc_profile.py)）：`primary_font_family`、`disable_rich_text_translate`、`split_short_lines`、`short_line_split_factor`、`merge_alternating_line_numbers`。
- **被 HPD 扫描件链路强制覆盖** —— `pdf_needs_hpd()` 自动判定 + 失败自动重试（gui.py:1110-1141、1197-1220）：`ocr_workaround`、`skip_scanned_detection`、`auto_enable_ocr_workaround`。
- **单引擎下的死选项** —— `enabled_services = "Ollama"` 只剩一个选项；`no_auto_extract_glossary = true` 使术语引擎整组 `term_*`（6 项 + 引擎详情）全程不跑：`service`、`enable_auto_term_extraction`、`term_*`、各家 API key/model。
- **运维参数，不该暴露给业务用户** —— `rate_limit_mode` / `rpm` / `concurrent_threads` / `custom_qps` / `pool_max_workers`（已按 Ollama 单实例固化）、`custom_system_prompt_input`、`min_text_length`、`rpc_doclayout`、`max_pages_per_part`、`ollama_model` / `ollama_host` / `num_predict`。
- **BabelDOC 内部调参，官方标注不建议更改** —— `formular_font_pattern`、`formular_char_pattern`、`non_formula_line_iou_threshold`、`figure_table_protection_threshold`、`skip_formula_offset_calculation`、`remove_non_formula_lines`、`skip_clean`、`enhance_compatibility`。
- **已被下载区取代** —— `no_mono` / `no_dual` / `dual_translate_first` / `use_alternating_pages_dual`（下载内容与格式已由 `download_content_mode` / `download_formats` 表达）。
- **有价值、值得前移** —— `doc_profile_dropdown`、`page_range` + `page_input`、`only_include_translated_page`、`glossary_file`、`ignore_cache`、`watermark_output_mode`、`lang_selector`、`save_btn`。

## 顺带修一个真 bug

`doc_profile_dropdown` 只在 `file_input.upload` 时经 `_qy_hint_doc_profile` 写入 `state["_doc_profile_ui"]`（[gui.py:7632-7654](/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py)），**没有 `.change` 绑定**。用户上传后手动改选模板不生效。前移时补上绑定。

## 目标左栏结构

```
## File(s)      Type / 上传框 / 已上传列表
## Translation Options
   语言行（from ⇄ to）
   文档类型模板            ← 常驻，从设置页搬来
   ▸ 高级选项（默认收起）   ← 新建 Accordion，填补左下空白
       页码范围 + 页码输入 + 仅输出译文页
       术语表（CSV）
       忽略缓存
       水印模式
       界面语言
       [保存设置]
## Translated（译后出现）下载区
[翻译] [取消]
```

## 实现

新增幂等补丁脚本 `scripts/apply-pdf2zh-settings-inline.py`，追加为 `pdf2zh.service` 的**最后一个** `ExecStartPre`（必须在 `apply-pdf2zh-office-preview.py` 之后，后者会整块重写 CSS）。

脚本做四件事：

1. **搬迁定义**：把下列控件的定义块从 `tab_settings` 内原位删除（替换为占位注释），按目标顺序重新缩进后插入到左栏 `with gr.Row(elem_classes=["action-row"]):`（[gui.py:6625](/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py)）之前：
   - 常驻：`doc_profile_dropdown`（7195-7201）
   - 新建 `with gr.Accordion("高级选项", open=False, elem_classes=["qy-adv-acc"]):` 内：`page_range`(7082) / `page_input`(7093) / `only_include_translated_page`(7100) / `glossary_file` + `require_llm_translator_inputs.append`(7203-7210) / `ignore_cache`(7318) / `watermark_output_mode`(7133) / `lang_selector.render()`(6665) / `save_btn`(7373)
   
   `require_llm_translator_inputs = []` 在 [gui.py:6505](/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py) 初始化，早于左栏，搬迁安全。`glossary_table` 留在原处（`visible=False`，仅作 `.change` 输出目标，定义仍早于 7745 的绑定）。

2. **修 bug**：在 `_qy_hint_doc_profile` 之后追加
   ```python
   doc_profile_dropdown.change(
       lambda c, st: ({**(st or {}), "_doc_profile_ui": c}),
       inputs=[doc_profile_dropdown, state], outputs=[state],
   )
   ```

3. **收敛入口**：`btn_main_tab` / `btn_settings_tab` 加 `visible=False`（保留对象，`_show_main_tab` / `_show_settings_tab` 绑定不动，零风险），`tab_settings` 保持 `visible=False` 永不打开。

4. **CSS**（追加到 `apply-pdf2zh-office-preview.py` 维护的 CSS 块尾部，或由本脚本独立追加一段带 marker 的 CSS）：
   - `.sidebar-nav { display: none !important; }` 收回 70px 空列
   - `.settings-container { display: none !important; }` 兜底
   - `.qy-adv-acc` 折叠面板与 `.qy-col-left > * { flex: 0 0 auto }` 兼容；展开时靠左栏已有的 `overflow-y: auto` 内部滚动，页面仍不出现外层滚动条

## 验收

- `scripts/verify-plan-016.sh`：断言搬迁后 `doc_profile_dropdown` / `page_range` / `glossary_file` / `save_btn` 定义出现在 `action-row` 之前、`tab_settings` 之后不再出现；`ui_setting_controls` 与 `fixed_param_names` 长度一致且顺序未变；`.change` 绑定存在；`sidebar-nav` CSS 存在；`python3 -c "import ast; ast.parse(open(GUI).read())"` 语法通过。
- `docs/walkthroughs/WT-016-settings-inline.md`：重启服务后浏览器核对左栏结构、高级选项展开/收起不撑破一屏、手动改模板后翻译日志出现 `应用文档模板 letter` 等对应值、页码范围生效。
- 交付：feat 分支 → verify → 精确 commit → no-ff merge main → 推远程 → `systemctl restart pdf2zh` → WT 验收。
