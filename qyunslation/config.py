# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
"""DocuTranslate 配置模块 - 从环境变量读取默认值"""
import os
from typing import Optional
from pathlib import Path


def _get_exe_dir() -> Path:
    """Get the directory where the executable or script is located"""
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的 exe 目录
        return Path(sys.executable).parent
    else:
        # 普通 Python 脚本
        return Path(__file__).parent.parent


def _load_dotenv():
    """Load .env file"""
    from dotenv import load_dotenv
    env_path = None

    # 优先级顺序：
    # 1. 当前工作目录及其父目录
    # 2. exe/脚本所在目录
    current_dir = Path.cwd()
    exe_dir = _get_exe_dir()

    search_dirs = [current_dir] + list(current_dir.parents) + [exe_dir]

    for dir_path in search_dirs:
        candidate = dir_path / ".env"
        if candidate.exists():
            env_path = candidate
            break

    if env_path:
        load_dotenv(env_path)


# Load .env on module import
_load_dotenv()


def _dual_keys(suffix: str) -> tuple[str, str]:
    """QYUNSLATION_* 优先，回落 DOCUTRANSLATE_*。"""
    return f"QYUNSLATION_{suffix}", f"DOCUTRANSLATE_{suffix}"


def _env_get(suffix: str) -> Optional[str]:
    for key in _dual_keys(suffix):
        val = os.environ.get(key)
        if val is not None and val != "":
            return val
    # 区分「未设置」与「设为空」：任一前缀存在即视为已设置
    for key in _dual_keys(suffix):
        if key in os.environ:
            return os.environ.get(key) or ""
    return None


def _get_env_str(suffix: str, default: str = "") -> str:
    val = _env_get(suffix)
    return default if val is None else val


def _get_env_int(suffix: str, default: int) -> int:
    val = _env_get(suffix)
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return default


def _get_env_float(suffix: str, default: float) -> float:
    val = _env_get(suffix)
    if val:
        try:
            return float(val)
        except ValueError:
            pass
    return default


def _get_env_bool(suffix: str, default: bool) -> bool:
    val = _env_get(suffix)
    if val is not None:
        return val.lower() in ("true", "1", "yes", "on")
    return default


def _get_env_optional_int(suffix: str) -> Optional[int]:
    val = _env_get(suffix)
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return None


def _get_env_optional_str(suffix: str) -> Optional[str]:
    val = _env_get(suffix)
    return val if val else None


def _is_env_set(suffix: str) -> bool:
    """检查环境变量是否被实际设置（非空）；QYUNSLATION_* 优先。"""
    val = _env_get(suffix)
    return val is not None and val != ""


# ============================================================
# BaseWorkflowParams 默认值
# ============================================================
API_KEY = _get_env_str("API_KEY", "xx")
BASE_URL = _get_env_str("BASE_URL", "")
MODEL_ID = _get_env_str("MODEL_ID", "")
TO_LANG = _get_env_str("TO_LANG", "中文")
SKIP_TRANSLATE = _get_env_bool("SKIP_TRANSLATE", False)
CHUNK_SIZE = _get_env_int("CHUNK_SIZE", 4000)
CONCURRENT = _get_env_int("CONCURRENT", 30)
TEMPERATURE = _get_env_float("TEMPERATURE", 0.7)
TOP_P = _get_env_float("TOP_P", 0.9)
TIMEOUT = _get_env_int("TIMEOUT", 1200)
THINKING = _get_env_str("THINKING", "disable")
RETRY = _get_env_int("RETRY", 2)
SYSTEM_PROXY_ENABLE = _get_env_bool("SYSTEM_PROXY_ENABLE", False)
CUSTOM_PROMPT = _get_env_str("CUSTOM_PROMPT", "")
FORCE_JSON = _get_env_bool("FORCE_JSON", False)
RPM = _get_env_optional_int("RPM")
TPM = _get_env_optional_int("TPM")
PROVIDER = _get_env_optional_str("PROVIDER")
EXTRA_BODY = _get_env_str("EXTRA_BODY", "")
GLOSSARY_GENERATE_ENABLE = _get_env_bool("GLOSSARY_GENERATE_ENABLE", False)
TLS_VERIFY = _get_env_bool("TLS_VERIFY", True)

# 环境变量是否被实际设置的标记（用于强制覆盖逻辑）
ENV_SET = {
    "api_key": _is_env_set("API_KEY"),
    "base_url": _is_env_set("BASE_URL"),
    "model_id": _is_env_set("MODEL_ID"),
    "to_lang": _is_env_set("TO_LANG"),
    "provider": _is_env_set("PROVIDER"),
    "thinking": _is_env_set("THINKING"),
    "chunk_size": _is_env_set("CHUNK_SIZE"),
    "concurrent": _is_env_set("CONCURRENT"),
    "temperature": _is_env_set("TEMPERATURE"),
    "top_p": _is_env_set("TOP_P"),
    "retry": _is_env_set("RETRY"),
    "system_proxy_enable": _is_env_set("SYSTEM_PROXY_ENABLE"),
    "custom_prompt": _is_env_set("CUSTOM_PROMPT"),
    "force_json": _is_env_set("FORCE_JSON"),
    "rpm": _is_env_set("RPM"),
    "tpm": _is_env_set("TPM"),
    "extra_body": _is_env_set("EXTRA_BODY"),
}

# ============================================================
# 环境变量默认值模式（仅影响 Web 前端）
# ============================================================
WEB_SKIP_VALIDATION = _get_env_bool("WEB_SKIP_VALIDATION", False)
# 是否强制使用环境变量的值（仅对 API_KEY, BASE_URL, MODEL_ID, PROVIDER 生效）
# 设为 true 时，无论前端是否传参，都强制使用 .env 中的值
# 设为 false 时，仅当前端传参为空时才使用 .env 中的值
ENV_FORCE_OVERRIDE = _get_env_bool("ENV_FORCE_OVERRIDE", False)

# ============================================================
# MarkdownWorkflowParams 默认值
# ============================================================
CONVERT_ENGINE = _get_env_str("CONVERT_ENGINE", "identity")
MD2DOCX_ENGINE = _get_env_str("MD2DOCX_ENGINE", "auto")
MINERU_TOKEN = _get_env_str("MINERU_TOKEN", "")
MODEL_VERSION = _get_env_str("MODEL_VERSION", "vlm")
FORMULA_OCR = _get_env_bool("FORMULA_OCR", True)
CODE_OCR = _get_env_bool("CODE_OCR", True)
MINERU_LANGUAGE = _get_env_str("MINERU_LANGUAGE", "ch")
MINERU_DEPLOY_BASE_URL = _get_env_str("MINERU_DEPLOY_BASE_URL", "http://127.0.0.1:8000")
MINERU_DEPLOY_BACKEND = _get_env_str("MINERU_DEPLOY_BACKEND", "hybrid-auto-engine")
MINERU_DEPLOY_PARSE_METHOD = _get_env_str("MINERU_DEPLOY_PARSE_METHOD", "auto")
MINERU_DEPLOY_TABLE_ENABLE = _get_env_bool("MINERU_DEPLOY_TABLE_ENABLE", True)
MINERU_DEPLOY_FORMULA_ENABLE = _get_env_bool("MINERU_DEPLOY_FORMULA_ENABLE", True)
MINERU_DEPLOY_START_PAGE_ID = _get_env_int("MINERU_DEPLOY_START_PAGE_ID", 0)
MINERU_DEPLOY_END_PAGE_ID = _get_env_int("MINERU_DEPLOY_END_PAGE_ID", 99999)
MINERU_DEPLOY_SERVER_URL = _get_env_str("MINERU_DEPLOY_SERVER_URL", "")

# ============================================================
# TextWorkflowParams 默认值
# ============================================================
INSERT_MODE = _get_env_str("INSERT_MODE", "replace")
SEPARATOR = _get_env_str("SEPARATOR", "\n")
SEGMENT_MODE = _get_env_str("SEGMENT_MODE", "line")

# ============================================================
# 系统参数
# ============================================================
PORT = _get_env_int("PORT", 8010)
PROXY_ENABLED = _get_env_bool("PROXY_ENABLED", False)
CACHE_NUM = _get_env_int("CACHE_NUM", 10)
API_TOKEN = _get_env_optional_str("API_TOKEN")
TASK_TTL_HOURS = _get_env_int("TASK_TTL_HOURS", 24)

# ============================================================
# 兼容旧版 default_params
# ============================================================
default_params = {
    "thinking": THINKING,
    "chunk_size": CHUNK_SIZE,
    "concurrent": CONCURRENT,
    "temperature": TEMPERATURE,
    "top_p": TOP_P,
    "timeout": TIMEOUT,
    "retry": RETRY,
    "system_proxy_enable": SYSTEM_PROXY_ENABLE,
    "extra_body": EXTRA_BODY,
    "web_skip_validation": WEB_SKIP_VALIDATION,
    "env_force_override": ENV_FORCE_OVERRIDE,
    # 内置大模型引擎：隐藏 AISettings 后，前端 model_id/base_url/provider 用 .env 默认值
    "model_id": MODEL_ID,
    "base_url": BASE_URL,
    "provider": PROVIDER,
    "to_lang": TO_LANG,
}
