# PLAN-001b：质量门禁成果入库 + 构建产物治理

修 D1、D8。

## 变更

- `segments_agent.py`：拒绝原文兜底，新增 `_assemble_translated_segments`
- `core/schemas.py`：`ENV_FORCE_OVERRIDE` 仅覆盖连接字段
- `server/core.py`：日志 seq、失败门禁
- `app.py` + `useTasks.js`：增量日志 `?since=`
- `docx_translator.py`：段落完整性校验
- 清理 `static/assets/` 陈旧 bundle

## 验证

- V1：`pytest tests/` 75 通过
- V2：git clean
- V3：index.html 引用 asset 存在且唯一
