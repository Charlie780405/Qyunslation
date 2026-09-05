"""
Tests for global_values module
"""
import os
import pytest

from qyunslation.global_values import USE_PROXY


def test_use_proxy_disabled_by_default():
    """Test that USE_PROXY is disabled by default"""
    # Clear any existing proxy env var
    if "DOCUTRANSLATE_PROXY_ENABLED" in os.environ:
        del os.environ["DOCUTRANSLATE_PROXY_ENABLED"]

    # Import again to reload the value
    from importlib import reload
    import qyunslation.global_values
    reload(qyunslation.global_values)

    assert qyunslation.global_values.USE_PROXY == False


def test_use_proxy_enabled_when_env_var_set():
    """Test that USE_PROXY is enabled when DOCUTRANSLATE_PROXY_ENABLED is set to true"""
    os.environ["DOCUTRANSLATE_PROXY_ENABLED"] = "true"

    # Import again to reload the value
    from importlib import reload
    import qyunslation.global_values
    reload(qyunslation.global_values)

    assert qyunslation.global_values.USE_PROXY == True

    # Clean up
    del os.environ["DOCUTRANSLATE_PROXY_ENABLED"]


def test_use_proxy_disabled_when_env_var_set_to_false():
    """Test that USE_PROXY is disabled when DOCUTRANSLATE_PROXY_ENABLED is set to false"""
    os.environ["DOCUTRANSLATE_PROXY_ENABLED"] = "false"

    # Import again to reload the value
    from importlib import reload
    import qyunslation.global_values
    reload(qyunslation.global_values)

    assert qyunslation.global_values.USE_PROXY == False

    # Clean up
    del os.environ["DOCUTRANSLATE_PROXY_ENABLED"]


def test_use_proxy_case_insensitive():
    """Test that DOCUTRANSLATE_PROXY_ENABLED is case insensitive"""
    os.environ["DOCUTRANSLATE_PROXY_ENABLED"] = "TRUE"

    # Import again to reload the value
    from importlib import reload
    import qyunslation.global_values
    reload(qyunslation.global_values)

    assert qyunslation.global_values.USE_PROXY == True

    os.environ["DOCUTRANSLATE_PROXY_ENABLED"] = "True"
    reload(qyunslation.global_values)
    assert qyunslation.global_values.USE_PROXY == True

    # Clean up
    del os.environ["DOCUTRANSLATE_PROXY_ENABLED"]
