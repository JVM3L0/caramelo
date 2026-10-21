"""HTTP plumbing shared by the store integrations."""

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx


def build_http_client(user_agent: str, proxy: str | None = None) -> httpx.AsyncClient:
    """Shared client for store integrations. Proxy is off unless configured."""
    return httpx.AsyncClient(
        proxy=proxy,
        headers={"User-Agent": user_agent, "Accept-Language": "pt-BR,pt;q=0.9"},
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
    )


class Throttle:
    """Keeps at least `min_interval` seconds between requests to one store."""

    def __init__(
        self,
        min_interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delay = self._next_at - self._clock()
            if delay > 0:
                await self._sleep(delay)
            self._next_at = self._clock() + self._min_interval
