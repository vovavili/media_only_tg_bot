"""Get full test coverage for the conftest fixtures themselves."""

from __future__ import annotations

import logging
from unittest.mock import Mock

from src.make_utils import Settings


def test_mock_settings(mock_settings: Mock) -> None:
    """Test mock_settings fixture."""
    assert isinstance(mock_settings, Mock)
    assert mock_settings.GROUP_CHAT_ID == 123456
    assert mock_settings.TOPIC_ID == 789
    assert mock_settings.ENVIRONMENT == "development"
    assert mock_settings._spec_class == Settings


def test_mock_logger(mock_logger: Mock) -> None:
    """Test mock_logger fixture."""
    assert isinstance(mock_logger, Mock)

    # Test all logging methods
    messages = {
        "info": "Info message",
        "error": "Error message",
        "warning": "Warning message",
        "critical": "Critical message",
        "debug": "Debug message",
    }

    for method, message in messages.items():
        getattr(mock_logger, method)(message)
        getattr(mock_logger, method).assert_called_once_with(message)

    # Verify all methods were created
    for method in messages:
        assert hasattr(mock_logger, method)
        assert isinstance(getattr(mock_logger, method), Mock)


def test_create_log_record_default() -> None:
    """Test create_log_record with default values."""
    from tests.conftest import create_log_record

    record = create_log_record()
    assert record.name == "test_module"
    assert record.levelno == logging.INFO
    assert record.msg == "Test message"
    assert record.args == ()
    assert record.pathname == "test.py"
    assert record.lineno == 1
    assert record.exc_info is None


def test_create_log_record_custom() -> None:
    """Test create_log_record with custom values."""
    from tests.conftest import create_log_record

    record = create_log_record(
        module="custom_module",
        level=logging.ERROR,
        msg="Custom message",
        args=("arg1", {"key": "value"}),
    )
    assert record.name == "custom_module"
    assert record.levelno == logging.ERROR
    assert record.msg == "Custom message"
    assert record.args == ("arg1", {"key": "value"})
