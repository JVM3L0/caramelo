"""Read side for operators: what is being collected and how healthy it is.

These are queries only; nothing here talks to a store or changes data, so looking at the
dashboard never adds load to anyone.
"""

import statistics
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
    # Last prices in cents, oldest first, for a mini chart. Sold-out collections are skipped.
    trend: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class QueueStats:
    pending: int
    running: int
    failed: int
    oldest_pending_at: datetime | None


@dataclass(frozen=True, slots=True)
class HistoryPoint:
    collected_at: datetime
    pix: Price | None
    card: Price | None
    in_stock: bool


@dataclass(frozen=True, slots=True)
class ListingHistory:
    listing_id: ListingId
    source_id: SourceId
    title: str
    url: str
    # Oldest first.
    points: tuple[HistoryPoint, ...]


@dataclass(frozen=True, slots=True)
class PriceSummary:
    collections: int
    in_stock_collections: int
    lowest: Price | None
    highest: Price | None
    median: Price | None
    current: Price | None
    # How far the current price is from the median (-0.1 = 10% below it).
    vs_median: float | None


def summarize(history: ListingHistory) -> PriceSummary:
    """Pix price (card when there is no Pix) over the in-stock collections."""

    def best(point: HistoryPoint) -> Price | None:
        return point.pix or point.card

    prices = [b for p in history.points if p.in_stock and (b := best(p)) is not None]
    cents = [price.cents for price in prices]
    last = history.points[-1] if history.points else None
    current = best(last) if last is not None and last.in_stock else None
    median = Price(round(statistics.median(cents))) if cents else None
    vs_median = (current.cents - median.cents) / median.cents if current and median else None
    return PriceSummary(
        collections=len(history.points),
        in_stock_collections=sum(p.in_stock for p in history.points),
        lowest=Price(min(cents)) if cents else None,
        highest=Price(max(cents)) if cents else None,
        median=median,
        current=current,
        vs_median=vs_median,
    )


@dataclass(frozen=True, slots=True)
class ActivityBucket:
    hour: datetime
    points: int


class DashboardQueries(Protocol):
    async def source_health(
        self, now: datetime, overdue_after: timedelta = timedelta(minutes=10)
    ) -> list[SourceHealth]: ...

    async def listings(self, query: ListingQuery) -> list[ListingRow]: ...

    async def history(
        self, listing_id: ListingId, since: datetime, limit: int = 2000
    ) -> ListingHistory | None:
        """The listing's collections since `since` (the newest `limit` of them)."""
        ...

    async def activity(self, now: datetime, hours: int = 24) -> list[ActivityBucket]:
        """Price points collected per hour for the last `hours` hours, empty hours included."""
        ...


class QueueStatistics(Protocol):
    async def stats(self) -> QueueStats: ...
