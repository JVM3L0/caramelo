"""Read side for operators: what is being collected and how healthy it is.

These are queries only; nothing here talks to a store or changes data, so looking at the
dashboard never adds load to anyone.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol

from caramelo.domain.ids import ListingId, SourceId
from caramelo.domain.money import Price

type ListingOrder = Literal["recent", "price", "change", "title"]

LISTING_ORDERS: tuple[ListingOrder, ...] = ("recent", "price", "change", "title")


@dataclass(frozen=True, slots=True)
class SourceHealth:
    source_id: SourceId
    monitored: int
    sold_out: int
    price_points: int
    points_last_hour: int
    last_collected_at: datetime | None
    next_collect_at: datetime | None
    # Monitored listings whose collection is late by more than the grace period.
    overdue: int
    # Requests per hour the configured intervals add up to (a load estimate).
    estimated_requests_per_hour: float


@dataclass(frozen=True, slots=True)
class ListingQuery:
    search: str = ""
    in_stock: bool | None = None
    changed_only: bool = False
    order: ListingOrder = "recent"
    limit: int = 200


@dataclass(frozen=True, slots=True)
class ListingRow:
    listing_id: ListingId
    source_id: SourceId
    external_id: str
    title: str
    url: str
    pix: Price | None
    card: Price | None
    in_stock: bool
    collected_at: datetime
    points: int
    next_collect_at: datetime | None
    # Relative change of the price against the previous collection (-0.08 = 8% cheaper).
    change: float | None


@dataclass(frozen=True, slots=True)
class QueueStats:
    pending: int
    running: int
    failed: int
    oldest_pending_at: datetime | None


class DashboardQueries(Protocol):
    async def source_health(
        self, now: datetime, overdue_after: timedelta = timedelta(minutes=10)
    ) -> list[SourceHealth]: ...

    async def listings(self, query: ListingQuery) -> list[ListingRow]: ...


class QueueStatistics(Protocol):
    async def stats(self) -> QueueStats: ...
