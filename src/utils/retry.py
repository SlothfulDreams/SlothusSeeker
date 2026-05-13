"""Retry logic with exponential backoff for network operations."""

import asyncio
from typing import Awaitable, Callable, TypeVar

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

T = TypeVar("T")


async def retry_with_backoff(
    func: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay after each retry
        exceptions: Tuple of exception types to catch and retry

    Returns:
        Result from the function

    Raises:
        The last exception if all retries fail
    """
    delay = initial_delay
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt < max_retries - 1:
                logger.warning(
                    "Attempt %s/%s failed: %s. Retrying in %.1fs...",
                    attempt + 1,
                    max_retries,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                logger.error("All %s attempts failed", max_retries)

    if last_exception is None:
        raise RuntimeError("retry_with_backoff exhausted without capturing an error")

    raise last_exception
