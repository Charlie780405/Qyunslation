# PLAN-071f：源译双画布预览与任务详情

> 状态：**已实现（浏览器证据 BLOCKED）**
> 父计划：[PLAN-071](./README.md)
> 依赖：[071d](./PLAN-071d-stage-events-progress.md)、[071e](./PLAN-071e-qa-term-gate-formal.md)

## 目标

`/workbench/:runId` 成为真正的任务详情页；桌面源译并排、平板页签、手机单画布；四类格式可在浏览器对照预览；刷新后恢复页码、缩放和选中对象。

## 现状

- `router.js`：`/workbench` 与 `/workbench/:runId` 均挂 `WorkbenchPage`；页面不消费 `runId`。
- Next 工作台无 PDF 预览、无 Inspector。
- Legacy：`PreviewOffcanvas.vue` + `usePreview.js` 用 iframe/blob，无 pdf.js；有 sync scroll。
- 前端无 vitest/playwright/axe（`frontend/package.json` 仅 build 脚本）。
- LibreOffice：部署侧已用于 Office 链路；需确认 `soffice` 在生产 PATH（071a 基线应记录）。

## 任务

### Task 0：前端测试基建（前置）

- 为 `frontend/` 增加 `vitest`、`@vue/test-utils`、`axe-core` 与 npm scripts。
- 最小 smoke：router 解析、`StageTimeline` 渲染。

**验收：** `npm test` 在 CI/本地可跑通至少 1 个用例。

### Task 1：RunDetailPage 路由拆分

- 新增 `frontend/src/next/pages/RunDetailPage.vue`。
- `router.js`：`/workbench/:runId` → `RunDetailPage`；列表保持 `WorkbenchPage`。
- 列表行点击 `router.push(/workbench/${id})`。
- 拉取 `getRun`、`events`、`qa-items`、artifacts 元数据。

**验收：** 深链刷新仍停留在同一 run；错误 runId 显示可恢复错误态。

### Task 2：预览产物与 API

- 服务端：
  - PDF：源文件与译文 PDF 作为 preview 流。
  - DOCX/PPTX：`soffice --headless` 转为受保护 PDF，kind=`source_preview`/`translated_preview`；原始可编辑文件仍为独立产物。
  - 图片：直接字节流。
- `GET .../preview/source`、`GET .../preview/translated`：会话鉴权、HTTP Range、`Content-Disposition: inline`、不暴露存储路径、校验 generation。

**验收：** API 测试覆盖 401/403/Range/跨租户；Office 转换失败有明确错误码。

### Task 3：双画布与交互

- 引入 `pdfjs-dist`，按页懒加载。
- 桌面并排；`matchMedia` 平板页签；手机默认单画布（可切换源/译）。
- 页码、缩放、适宽、旋转、同步滚动与解除同步。
- 源文件预检完成后即可预览；译文页面渲染完成后渐进出现。
- store：`frontend/src/next/stores/runDetail.js`；页码/缩放/选中对象/`sync` 写入 URL query。

**验收：** 组件测试 + 手动 Chrome 证据（正式发布在 071i）；刷新恢复 query 状态。

### Task 4：对象检查器与日志抽屉

- 点击 Manifest 对象打开检查器：源文、译文、术语命中、QA、修订历史（数据来自 qa-items + term 解析，与 071e/071h 同源）。
- 技术日志继续放抽屉，不占主画布。
- 阶段条复用 071d `StageTimeline`，详情与列表同一事件源。

**验收：** 选中对象 URL 可分享；日志抽屉不遮挡画布关键控件。

## 数据库 / 接口变更

- 预览接口（见上）
- artifact kind 扩展已在 071e；本任务负责生成 preview 类产物
- 无强制新表

## 测试文件

- `frontend` vitest：`RunDetailPage`、`StageTimeline`、URL 状态
- `tests/api/test_plan071f_preview_range.py`
- `tests/api/test_plan071f_office_preview.py`
- `tests/ui/test_plan071f_run_detail_route.py`

## 完成门槛

- 四类格式都能在浏览器中对照预览。
- 刷新后恢复页码、缩放和选中对象。
- 阶段条不再使用硬编码理想流。

## 验证命令

```bash
cd frontend && npm test
pytest -q tests/api/test_plan071f_preview_range.py tests/api/test_plan071f_office_preview.py \
  tests/ui/test_plan071f_run_detail_route.py
```

## 不做

- 不在本子计划完成全量 E2E 发布签字（071i + 真实 Chrome DevTools）。
- 不重做术语工作台页面。
- 不用 Gradio inspector 补丁替代 Vue 检查器。
