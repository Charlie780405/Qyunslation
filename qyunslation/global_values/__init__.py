# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
import os

from .conditional_import import available_packages, conditional_import


def _proxy_enabled() -> bool:
    for key in ("QYUNSLATION_PROXY_ENABLED", "DOCUTRANSLATE_PROXY_ENABLED"):
        val = os.getenv(key)
        if val is not None and val != "":
            return val.lower() == "true"
    return False


USE_PROXY = _proxy_enabled()
if USE_PROXY:
    print(f"USE_PROXY:{USE_PROXY}")
