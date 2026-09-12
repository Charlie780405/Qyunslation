# PLAN-047a 交付闭环

- `scripts/deploy-translate-stack.sh` 同时重启 pdf2zh + qyunslation-office，核对指纹
- `/service/image-translate-health` 返回 `code_fingerprint` + capabilities
- `assert_sidecar_in_sync()` 不一致硬失败（`QYUNSLATION_REQUIRE_SIDECAR_SYNC=1`）
