from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import timedelta

from caramelo.application.ports import Clock, DealSource, UnitOfWork
from caramelo.application.use_cases.recording import record_offer
from caramelo.domain.catalog import CollectionSchedule, Listing
from caramelo.domain.ids import SourceId
from caramelo.domain.pricing import PricePoint


class UnknownStoreUrl(Exception):
    def __init__(self, url: str) -> None:
        super().__init__(f"no store integration recognizes this URL: {url}")


class ProductNotFound(Exception):
    def __init__(self, url: str) -> None:
        super().__init__(f"the store returned no offer for: {url}")


@dataclass(frozen=True, slots=True)
class Monitored:
    listing: Listing
    first_price: PricePoint


class MonitorListing:
    """Adds a product URL to the monitored catalog.

    It is collected once right away, which validates the URL and fills the title.
    """

    def __init__(
        self,
        sources: Mapping[SourceId, DealSource],
        uow_factory: Callable[[], UnitOfWork],
        clock: Clock,
    ) -> None:
        self._sources = sources
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, url: str, interval: timedelta) -> Monitored:
        source, external_id = self._resolve(url)
        offer = await anext(aiter(source.fetch([external_id])), None)
        if offer is None:
            raise ProductNotFound(url)

        now = self._clock.now()
        schedule = CollectionSchedule.starting(now, interval)
        async with self._uow_factory() as uow:
            listing, point = await record_offer(uow, offer, now)
            await uow.catalog.set_schedule(listing.id, schedule)
            await uow.commit()
        return Monitored(replace(listing, schedule=schedule), point)

    def _resolve(self, url: str) -> tuple[DealSource, str]:
        for source in self._sources.values():
            external_id = source.external_id_from_url(url)
            if external_id is not None:
                return source, external_id
        raise UnknownStoreUrl(url)
