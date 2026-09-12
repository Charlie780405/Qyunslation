---
name: translate-stack-process-boundary
description: >-
  翻译栈进程边界：pdf2zh 与 qyunslation-office sidecar 双进程、代码指纹、QC 过边界。
  触发：改了没效果、依然如故、没生效、重启、sidecar、8010、no local rapidocr、
  object_qc 为空、QC 没告警、缺陷没被发现、代码指纹、deploy-translate-stack、
  QC_CHANNEL_BLIND、PLAN-047a、PLAN-047b。
---

# 翻译栈进程边界（SK-Q004）

## 诊断三问

1. 我改的代码在**哪个进程**跑？证据是 `ps -o lstart` 还是猜的？
2. 这个改动失败时，失败模式是「难看」还是「消失」？
3. 缺陷发生时谁会告诉我——如果答案是「用户截图」，先去修质检。

## 铁律

### A. 部署

1. **改 `qyunslation/extensions/**` 必须重启 `qyunslation-office.service`**——嵌字全部跑在 :8010 sidecar，独立 venv。
2. **改 `scripts/apply-pdf2zh-*.py` / `doc_profile.py` 必须重启 `pdf2zh.service`**。
3. **两者都改就都重启**——统一走 `bash scripts/deploy-translate-stack.sh`。
4. **"改了没效果"的第一诊断动作是 `ps -o lstart` 比对文件 mtime，而不是读代码。**

| 症状 | 先查 | 修法 | 判据 |
| --- | --- | --- | --- |
| 改了嵌字逻辑依然如故 | sidecar `ActiveEnterTimestamp` vs `image_translate.py` mtime | `deploy-translate-stack.sh` | 双侧指纹一致 |
| 只重启了 pdf2zh | journalctl 是否有 `no local rapidocr, routing ... sidecar` | 必启 office | health 端点可达 |

### B. 质检过边界

5. **跨进程返回值里 QC 写 `{}` 等于质检瞎**——必须显式搬运（`X-Image-QC` 响应头）并标注 `qc_channel`。
6. **`object_qc` 全空且 `blocks>0` 视为可疑，不视为干净**——记 `QC_CHANNEL_BLIND`。

| 症状 | 先查 | 修法 | 判据 |
| --- | --- | --- | --- |
| imgtr.json 全是 `object_qc: []` | `qc_channel` 字段是否存在 | 解析 `X-Image-QC` | channel=sidecar 且至少一条非空 |
| 缺陷零告警交付 | sidecar 是否回传 QC | custom_api 用 `translate_image_with_qc` | verify 断言非空率>0 |

## 相关文件

- `scripts/deploy-translate-stack.sh`
- `scripts/pdf_image_translate.py`（`assert_sidecar_in_sync`）
- `qyunslation/custom_api.py`（`/service/image-translate-health`）
- `qyunslation/extensions/image_translate.py`（`code_fingerprint` / `capability_probe`）
