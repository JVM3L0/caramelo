"""In-memory implementations of the ports, for use-case tests."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self

from caramelo.domain.catalog import Listing
from caramelo.domain.ids import ListingId, SourceId, new_id
from caramelo.domain.offers import RawOffer
from caramelo.domain.pricing import PricePoint


class FakeClock:
    def __init__(self, start: datetime | None = None, step: timedelta = timedelta(seconds=1)):
        self._now = start or datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
        self._step = step

    def now(self) -> datetime:
        current = self._now
        self._now += self._step
        return current


class FakeSource:
    def __init__(self, source_id: str, offers: list[RawOffer]) -> None:
        self._id = SourceId(source_id)
        self._offers = offers

    @property
    def id(self) -> SourceId:
        return self._id

    async def fetch(self) -> AsyncIterator[RawOffer]:
        for offer in self._offers:
            yield offer


class FakeCatalog:
    def __init__(self) -> None:
        self.listings: dict[tuple[str, str], Listing] = {}

    async def upsert_listing(self, offer: RawOffer, seen_at: datetime) -> Listing:
        key = (offer.source_id, offer.external_id)
        listing = self.listings.get(key)
        if listing is None:
            listing = Listing(
                id=ListingId(new_id()),
                source_id=offer.source_id,
                external_id=offer.external_id,
                url=offer.url,
                title=offer.title,
            )
            self.listings[key] = listing
        listing.title, listing.url = offer.title, offer.url
        return listing


class FakePriceHistory:
    def __init__(self) -> None:
        self.points: list[PricePoint] = []

    async def append(self, point: PricePoint) -> None:
        self.points.append(point)


class FakeUnitOfWork:
    """Shares its repositories across instances; records commits."""

    def __init__(self, catalog: FakeCatalog, prices: FakePriceHistory) -> None:
        self.catalog = catalog
        self.prices = prices
        self.commits = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1
