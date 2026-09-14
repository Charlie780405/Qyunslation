# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
import logging



# 创建日志对象
global_logger = logging.getLogger("TranslaterLogger")
global_logger.setLevel(logging.DEBUG)
# 输出到控制台；日志器保持 DEBUG 以便测试/调用方捕获，生产 handler 负责过滤。
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
global_logger.addHandler(console_handler)


def configure_runtime_logging() -> None:
    """恢复应用运行时的日志策略，并修复已创建 logger 的禁用状态。"""
    # Alembic's fileConfig used to disable existing loggers in-process.  Make
    # application startup self-healing for already-created logger instances.
    global_logger.disabled = False
    global_logger.setLevel(logging.INFO)
    global_logger.propagate = False
    for handler in global_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(logging.INFO)
