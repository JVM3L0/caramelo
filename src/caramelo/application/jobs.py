"""Background job contract, shared by whoever enqueues jobs and whatever queue runs them."""

from collections.abc import Awaitable, Callable

# A job is an async callable taking only JSON-serializable keyword arguments.
type JobHandler = Callable[..., Awaitable[None]]

COLLECT_SOURCE = "collect_source"
