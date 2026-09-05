# PLAN-006c：模型与并发校准

- `.env`：`CONCURRENT=8`、`TIMEOUT=300`、`CHUNK_SIZE=8000`（JSON 完整性回归通过）
- systemd `office.env` 仍可覆盖为 `CONCURRENT=4`（实测拐点附近）
- 脚本：`scripts/benchmark-plan-006c.py`
- 继续使用泰州 `qwen3.6:35b-a3b`，`THINKING=disable`
