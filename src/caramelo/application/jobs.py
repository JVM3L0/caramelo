"""Background job contract, shared by whoever enqueues jobs and whatever queue runs them."""

from collections.abc import Awaitable, Callable

# A job is an async callable taking only JSON-serializable keyword arguments; any result
# is ignored.
type JobHandler = Callable[..., Awaitable[object]]

# Payload: source_id: str, external_ids: list[str].
COLLECT_LISTINGS = "collect_listings"
# Periodic, no payload.
SCHEDULE_DUE_COLLECTIONS = "schedule_due_collections"

# Periodic jobs and their cron expressions.
PERIODIC: dict[str, str] = {SCHEDULE_DUE_COLLECTIONS: "* * * * *"}


def source_lock(source_id: str) -> str:
    """Serializes jobs that hit the same store, to stay polite and avoid blocks."""
    return f"source:{source_id}"
