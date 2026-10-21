from collections.abc import Callable, Sequence

from caramelo.application.ports import Clock, DealSource, UnitOfWork
from caramelo.application.use_cases.recording import record_offer


class CollectListings:
    """Fetches the current offers for some of a store's products and records them."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork], clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, source: DealSource, external_ids: Sequence[str]) -> int:
        recorded = 0
        async for offer in source.fetch(external_ids):
            # One transaction per offer: a bad item never discards the rest of the batch.
            async with self._uow_factory() as uow:
                await record_offer(uow, offer, self._clock.now())
                await uow.commit()
            recorded += 1
        return recorded
