'''Rate limiting utilities (placeholder)

This module provides a minimal ``limited_call`` helper that wraps an async
callable. In production you might add token‑bucket or exponential back‑off
logic, but for the current prototype we simply await the coroutine.
''' 

from __future__ import annotations

from typing import Awaitable, Callable, Any


async def limited_call(fn: Callable[[], Awaitable[Any]]) -> Any:
    """Execute ``fn`` without any throttling.

    The signature matches the original design where callers provide a
    zero‑argument async callable (e.g. ``lambda: llm_client.chat_completion(...)``).
    ``limited_call`` returns the awaited result directly.  This keeps the
    service lightweight while satisfying the import path ``app.utils.rate_limit``.
    """
    return await fn()

__all__ = ["limited_call"]
