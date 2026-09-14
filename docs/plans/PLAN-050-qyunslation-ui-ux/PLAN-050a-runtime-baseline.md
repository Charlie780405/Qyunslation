# PLAN-050a：真实运行时与 UI 契约基线

> 状态：**完成**
> 父计划：[PLAN-050](./PLAN-050-qyunslation-ui-ux.md)
> 依赖：无

## 目标

确认用户实际访问的 UI、静态资源来源、服务入口、补丁顺序和 Manifest/API 契约，建立修改前基线。该子计划不改变用户行为。

## 任务

### Task 1：运行时归属

- 追踪 `scripts/pdf2zh.service`、Gradio 启动参数、`apply-pdf2zh-*.py` 和静态资源。
- 确认 `frontend/` 是否被生产服务加载；记录首页 DOM、网络资源和版本标识。
- 形成“唯一施工面”决策：Gradio 补丁链或 Vue 应用。

**验收：** 服务入口、最终资源、补丁顺序和浏览器截图均有证据；不得只凭源码推断。

### Task 2：界面数据契约

- 对照 `docs/contracts/document-structure-manifest-v1.md`、任务接口和现有预扫描状态。
- 列出页面、对象、计数、问题、参考文献保护、能力和任务代际字段。
- 定义缺字段、旧 schema、截断、失败和降级的 UI 映射。

**验收：** 形成字段映射表；UI 不需要解析日志或底层资源数。

### Task 3：视觉与交互基线

- 在 320/768/1024/1440px 截取当前页面。
- 记录上传、预扫描、翻译、取消、失败、下载和预览的当前路径。
- 标记焦点、裁切、日志占位、图片/表格计数和双栏同步问题。

**验收：** 形成 [WT-050a](../../walkthroughs/WT-050a-runtime-baseline.md)，包含截图、DOM/网络证据和缺陷表。

## 文件范围

- 可能读取：`scripts/pdf2zh.service`、`scripts/apply-pdf2zh-*.py`、`frontend/src/**`、Manifest 合同和现有 030i 计划。
- 可能新增：`docs/contracts/ui-runtime-050.md`、`tests/ui/test_runtime_surface_050.py`、WT-050a。

## 完成定义

- [x] 唯一施工面已确认并经人工复核。
- [x] UI 状态契约与 Manifest 字段一一映射。
- [x] 真实运行时视觉基线可复现。
- [x] 未修改生产 UI、未部署。
