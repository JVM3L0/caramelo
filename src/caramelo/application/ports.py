"""Interfaces the use cases depend on. Adapters implement them; nothing here knows
which store, database, queue or messaging platform sits behind them."""

from collections.abc import AsyncIterator
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from caramelo.domain.catalog import Listing
from caramelo.domain.channels import Channel, ChannelKind
from caramelo.domain.ids import SourceId, TenantId
from caramelo.domain.offers import Deal, RawOffer
from caramelo.domain.pricing import PricePoint

type JobPayload = str | int | float | bool | None


class Clock(Protocol):
    def now(self) -> datetime: ...


# --- Driven ports: stores ---------------------------------------------------


class DealSource(Protocol):
    """A store integration (API, feed or scraper)."""

    @property
    def id(self) -> SourceId: ...

    def fetch(self) -> AsyncIterator[RawOffer]: ...


# --- Driven ports: persistence ----------------------------------------------


class CatalogRepository(Protocol):
    async def upsert_listing(self, offer: RawOffer, seen_at: datetime) -> Listing: ...


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

    async def enqueue(self, job: str, **payload: JobPayload) -> None: ...


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
