"""Test utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from media_only_topic.utils import error_handler, retry
from tests.conftest import TEST_ERROR_MESSAGE, test_function

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.mark.asyncio
async def test_error_handler() -> None:
    """Test async error handler."""
    # Create mock context with error
    mock_context = MagicMock()
    mock_context.error = ValueError(TEST_ERROR_MESSAGE)

    # Create a mock logger
    mock_logger = MagicMock()

    # Test error handling
    with patch("media_only_topic.utils.logger", mock_logger):
        await error_handler(None, mock_context)
        mock_logger.error.assert_called_once_with(mock_context.error)


def test_retry_successful_first_attempt() -> None:
    """Test that a successful function execution works normally."""
    mock_func = Mock(return_value="success")
    decorated_func = retry(mock_func)

    result = decorated_func()

    assert result == "success"
    assert mock_func.call_count == 1


def test_retry_successful_after_failures() -> None:
    """Test that the function retries and eventually succeeds."""
    mock_func = Mock(side_effect=[ValueError, ValueError, "success"])
    decorated_func = retry(mock_func, retries=3)

    with patch("time.sleep") as mock_sleep:
        result = decorated_func()

    assert result == "success"
    assert mock_func.call_count == 3
    assert mock_sleep.call_count == 2  # Called twice (after first two failures)


def test_retry_all_attempts_fail() -> None:
    """Test that the function raises an exception after all retries fail."""
    mock_func = Mock(side_effect=ValueError("Test error"))
    decorated_func = retry(mock_func, retries=2)

    with (
        patch("time.sleep"),
        pytest.raises(ValueError, match=r"Failed after 2 retries\.") as exc_info,
    ):
        decorated_func()

    assert "Failed after 2 retries" in str(exc_info.value)
    assert mock_func.call_count == 2


def test_retry_with_custom_delay() -> None:
    """Test that the retry delay is respected."""
    mock_func = Mock(side_effect=[ValueError, "success"])
    decorated_func = retry(mock_func, retries=2, retry_delay=5)

    with patch("time.sleep") as mock_sleep:
        result = decorated_func()

    mock_sleep.assert_called_once_with(5)
    assert result == "success"


def test_retry_invalid_retries() -> None:
    """Test that the decorator raises ValueError for invalid retries value."""
    with pytest.raises(ValueError, match=r"'retries' must be a natural number"):
        retry(test_function, retries=0)


def test_retry_preserves_function_metadata() -> None:
    """Test that the decorator preserves the original function's metadata."""
    decorated_func = retry(test_function)

    assert decorated_func.__name__ == "test_function"
    assert decorated_func.__doc__ == "A dummy function for unit testing decorators."


def test_retry_with_arguments() -> None:
    """Test that the decorator works with functions that take arguments."""
    mock_func = Mock(return_value="success")
    decorated_func = retry(mock_func)

    result = decorated_func(1, test="value")

    mock_func.assert_called_once_with(1, test="value")
    assert result == "success"


def test_retry_as_decorator_with_params() -> None:
    """Test that the decorator works when used with parameters."""
    mock_func = Mock(side_effect=[ValueError, "success"])

    @retry(retries=2, retry_delay=1)
    def test_func() -> Any:
        return mock_func()

    with patch("time.sleep"):
        result = test_func()

    assert result == "success"
    assert mock_func.call_count == 2


def test_retry_preserves_exception_chain() -> None:
    """Test that the original exception is preserved in the exception chain."""
    original_error = ValueError("Original error")
    mock_func = Mock(side_effect=original_error)
    decorated_func = retry(mock_func, retries=1)

    with (
        patch("time.sleep"),
        pytest.raises(ValueError, match=r"Failed after 1 retry\.") as exc_info,
    ):
        decorated_func()

    assert exc_info.value.__cause__ == original_error


def test_retry_with_different_exceptions() -> None:
    """Test that the decorator handles different types of exceptions."""
    mock_func = Mock(side_effect=[ValueError("First error"), TypeError("Second error"), "success"])
    decorated_func = retry(mock_func, retries=3)

    with patch("time.sleep"):
        result = decorated_func()

    assert result == "success"
    assert mock_func.call_count == 3


def test_retry_single_retry_grammar() -> None:
    """Test that the error message uses correct grammar for single retry."""
    mock_func = Mock(side_effect=ValueError("Test error"))
    decorated_func = retry(mock_func, retries=1)

    with (
        patch("time.sleep"),
        pytest.raises(ValueError, match=r"Failed after 1 retry\.") as exc_info,
    ):
        decorated_func()

    assert "Failed after 1 retry." in str(exc_info.value)


def test_retry_multiple_retries_grammar() -> None:
    """Test that the error message uses correct grammar for multiple retries."""
    mock_func = Mock(side_effect=ValueError("Test error"))
    decorated_func = retry(mock_func, retries=2)

    with (
        patch("time.sleep"),
        pytest.raises(ValueError, match=r"Failed after 2 retries\.") as exc_info,
    ):
        decorated_func()

    assert "Failed after 2 retries." in str(exc_info.value)


@pytest.mark.asyncio
async def test_retry_with_async_function() -> None:
    """Test that the decorator works with async functions."""

    async def async_func() -> str:
        return "success"

    decorated_func = retry(async_func)
    result = await decorated_func()

    assert result == "success"


def test_retry_preserves_return_type_hints() -> None:
    """Test that the decorator preserves the return type hints of the original function."""
    decorated_func = retry(test_function)

    assert decorated_func.__annotations__ == test_function.__annotations__


def test_retry_with_generator_function() -> None:
    """Test that the decorator works with generator functions."""

    def generator_func() -> Generator[int, None, None]:
        yield 1
        yield 2
        yield 3

    decorated_func = retry(generator_func)
    result = list(decorated_func())

    assert result == [1, 2, 3]


@pytest.mark.parametrize(("retries", "expected_calls"), [(1, 1), (2, 2), (3, 3), (5, 5)])
def test_retry_different_retry_counts(retries: int, expected_calls: int) -> None:
    """Test that the decorator respects different retry counts."""
    mock_func = Mock(side_effect=ValueError("Test error"))
    decorated_func = retry(mock_func, retries=retries)

    with patch("time.sleep"), pytest.raises(ValueError, match=r"Failed after \d retr(?:y|ies)\."):
        decorated_func()

    assert mock_func.call_count == expected_calls
