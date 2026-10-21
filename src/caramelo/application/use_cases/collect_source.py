from collections.abc import Callable

from caramelo.application.ports import Clock, DealSource, UnitOfWork
from caramelo.domain.pricing import PricePoint


class CollectSource:
    """Pulls every offer from a store and records it in the price history.

    Every observation is stored, discounted or not: the history is what later
    tells a real discount from a fake one.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork], clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, source: DealSource) -> int:
        recorded = 0
        async for offer in source.fetch():
            now = self._clock.now()
            async with self._uow_factory() as uow:
                listing = await uow.catalog.upsert_listing(offer, seen_at=now)
                await uow.prices.append(
                    PricePoint(
                        listing_id=listing.id,
                        collected_at=now,
                        pix=offer.pix,
                        card=offer.card,
                        installments=offer.installments,
                        in_stock=offer.in_stock,
                    )
                )
                await uow.commit()
            recorded += 1
        return recorded
