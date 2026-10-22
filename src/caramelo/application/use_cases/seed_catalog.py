from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from caramelo.application.ports import Clock, DealSource, UnitOfWork
from caramelo.application.use_cases.recording import record_offer
from caramelo.domain.catalog import CollectionSchedule


@dataclass(frozen=True, slots=True)
class SeedResult:
    discovered: int
    newly_monitored: int
    already_monitored: int


class SeedCatalog:
    """Finds a category's products and puts them under monitoring.

    The category pages already carry prices, so the first price point of every product
    costs no extra request. First collections are spread across one interval so a large
    seed never turns into a burst of requests.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork], clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, source: DealSource, category: str, max_pages: int, interval: timedelta
    ) -> SeedResult:
        offers = [offer async for offer in source.discover(category, max_pages)]
        newly = 0
        for index, offer in enumerate(offers):
            now = self._clock.now()
            async with self._uow_factory() as uow:
                listing, _ = await record_offer(uow, offer, now)
                # Products already monitored keep their own schedule.
                if listing.schedule is None:
                    first_run = now + interval * (index + 1) / len(offers)
                    await uow.catalog.set_schedule(
                        listing.id, CollectionSchedule(interval, first_run)
                    )
                    newly += 1
                await uow.commit()
        return SeedResult(len(offers), newly, len(offers) - newly)
