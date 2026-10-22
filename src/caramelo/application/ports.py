"""Interfaces the use cases depend on. Adapters implement them; nothing here knows
which store, database, queue or messaging platform sits behind them."""

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from caramelo.domain.catalog import CollectionSchedule, Listing
from caramelo.domain.channels import Channel, ChannelKind
from caramelo.domain.ids import ListingId, SourceId, TenantId
from caramelo.domain.offers import Deal, RawOffer
from caramelo.domain.pricing import PricePoint

type JobPayload = str | int | float | bool | list[str] | None


class Clock(Protocol):
    def now(self) -> datetime: ...


# --- Driven ports: stores ---------------------------------------------------


class DealSource(Protocol):
    """A store integration (API, feed or scraper)."""

    @property
    def id(self) -> SourceId: ...

    def external_id_from_url(self, url: str) -> str | None:
        """The store's product id if the URL belongs to this store, else None."""
        ...

    def fetch(self, external_ids: Sequence[str]) -> AsyncIterator[RawOffer]:
        """Current offers for the given products; missing products are skipped."""
        ...

    def discover(self, category: str, max_pages: int) -> AsyncIterator[RawOffer]:
        """Offers listed in a category, up to `max_pages` pages. Costs one request per
        page, so it is the cheap way to find many products and read their prices."""
        ...


# --- Driven ports: persistence ----------------------------------------------


class CatalogRepository(Protocol):
    async def upsert_listing(self, offer: RawOffer, seen_at: datetime) -> Listing: ...

    async def set_schedule(
        self, listing_id: ListingId, schedule: CollectionSchedule | None
    ) -> None: ...

    async def claim_due(self, now: datetime, limit: int) -> list[Listing]:
        """Monitored listings due by `now`, already moved to their next slot so
        concurrent schedulers never claim the same listing twice."""
        ...


class PriceHistory(Protocol):
    async def append(self, point: PricePoint) -> None: ...


class UnitOfWork(Protocol):
    """One transaction across repositories. Leaving the block without commit() rolls back."""

    @property
    def catalog(self) -> CatalogRepository: ...

    @property
    def prices(self) -> PriceHistory: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


# --- Driven ports: background jobs ------------------------------------------


class TaskQueue(Protocol):
    """Schedules background jobs by name. The queue technology stays in its adapter."""

    async def enqueue(self, job: str, *, lock: str | None = None, **payload: JobPayload) -> None:
        """Jobs sharing a `lock` run one at a time, in enqueue order."""
        ...


# --- Driven ports: publishing -----------------------------------------------


class AffiliateLinker(Protocol):
    """Turns a product URL into the tenant's affiliate URL."""

    async def link(self, tenant_id: TenantId, url: str) -> str: ...


class CopyWriter(Protocol):
    """Writes the post text for a deal (template now, LLM later)."""

    async def write(self, deal: Deal, url: str) -> str: ...


class Publisher(Protocol):
    @property
    def kind(self) -> ChannelKind: ...

    async def publish(self, channel: Channel, text: str) -> str:
        """Sends the post and returns the platform's message id."""
        ...
