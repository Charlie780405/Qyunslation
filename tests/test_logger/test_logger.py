"""
Tests for logger module
"""
import logging

import pytest

from qyunslation.logger.logger import global_logger


@pytest.fixture(autouse=True)
def reset_global_logger():
    """Keep logger tests isolated from in-process migration/lifespan setup."""
    global_logger.setLevel(logging.DEBUG)
    global_logger.propagate = True
    global_logger.disabled = False
    yield
    global_logger.setLevel(logging.DEBUG)
    global_logger.propagate = True
    global_logger.disabled = False


def test_logger_initialization():
    """Test that logger is properly initialized"""
    assert isinstance(global_logger, logging.Logger)
    assert global_logger.name == "TranslaterLogger"
    assert global_logger.level == logging.DEBUG


def test_logger_has_console_handler():
    """Test that logger has a StreamHandler configured"""
    handlers = global_logger.handlers
    assert len(handlers) >= 1
    assert any(isinstance(h, logging.StreamHandler) for h in handlers)


def test_runtime_configuration_keeps_debug_records_visible_to_caplog(caplog):
    """Application startup must not disable pytest/root capture for this logger."""
    from qyunslation.logger.logger import configure_runtime_logging

    global_logger.setLevel(logging.INFO)
    global_logger.propagate = False
    global_logger.disabled = True
    configure_runtime_logging()

    assert global_logger.disabled is False
    assert global_logger.level == logging.INFO
    assert global_logger.propagate is False


def test_logger_can_log_messages(caplog):
    """Test that logger can log messages at different levels"""
    # Set caplog to capture DEBUG level
    caplog.set_level(logging.DEBUG)

    test_messages = [
        (logging.DEBUG, "Debug message"),
        (logging.INFO, "Info message"),
        (logging.WARNING, "Warning message"),
        (logging.ERROR, "Error message"),
        (logging.CRITICAL, "Critical message"),
    ]

    for level, message in test_messages:
        global_logger.log(level, message)

    # Check that all messages were logged
    for level, message in test_messages:
        assert any(
            record.levelno == level and message in record.message
            for record in caplog.records
        )
