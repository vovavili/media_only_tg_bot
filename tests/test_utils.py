"""Test utilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.utils import error_handler
from tests.conftest import TEST_ERROR_MESSAGE


@pytest.mark.asyncio
async def test_error_handler() -> None:
    """Test async error handler."""
    # Create mock context with error
    mock_context = MagicMock()
    mock_context.error = ValueError(TEST_ERROR_MESSAGE)

    # Create a mock logger
    mock_logger = MagicMock()

    # Test error handling
    with patch("src.utils.logger", mock_logger):
        await error_handler(None, mock_context)
        mock_logger.error.assert_called_once_with(mock_context.error)
