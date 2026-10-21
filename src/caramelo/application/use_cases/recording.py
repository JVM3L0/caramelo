from datetime import datetime

from caramelo.application.ports import UnitOfWork
from caramelo.domain.catalog import Listing
from caramelo.domain.offers import RawOffer
from caramelo.domain.pricing import PricePoint


async def record_offer(
    uow: UnitOfWork, offer: RawOffer, now: datetime
) -> tuple[Listing, PricePoint]:
    """Stores an observation, discounted or not: the history is what later tells a
    real discount from a fake one."""
    listing = await uow.catalog.upsert_listing(offer, seen_at=now)
    point = PricePoint(
        listing_id=listing.id,
        collected_at=now,
        pix=offer.pix,
        card=offer.card,
        installments=offer.installments,
        in_stock=offer.in_stock,
    )
    await uow.prices.append(point)
    return listing, point
