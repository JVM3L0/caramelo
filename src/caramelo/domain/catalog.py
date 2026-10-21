"""Product identity in three levels.

ProductFamily  -> what people search for   (RTX 4070 SUPER 12GB)
  Product      -> a concrete variant       (ASUS Dual RTX 4070 SUPER OC)
    Listing    -> that variant at a store  (Kabum SKU 123456)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from caramelo.domain.ids import FamilyId, ListingId, ProductId, SourceId


@dataclass(slots=True)
class ProductFamily:
    id: FamilyId
    name: str
    category: str


@dataclass(slots=True)
class Product:
    id: ProductId
    brand: str
    name: str
    family_id: FamilyId | None = None
    mpn: str | None = None
    ean: str | None = None


@dataclass(slots=True)
class Listing:
    id: ListingId
    source_id: SourceId
    external_id: str
    url: str
    title: str
    # Filled by product matching; unmatched listings still collect history.
    product_id: ProductId | None = None
    schedule: CollectionSchedule | None = None

    @property
    def monitored(self) -> bool:
        return self.schedule is not None


MIN_COLLECT_INTERVAL = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class CollectionSchedule:
    """How often a monitored listing is collected, and when it is due next."""

    interval: timedelta
    next_collect_at: datetime

    def __post_init__(self) -> None:
        if self.interval < MIN_COLLECT_INTERVAL:
            raise ValueError(f"collect interval must be at least {MIN_COLLECT_INTERVAL}")

    @classmethod
    def starting(cls, now: datetime, interval: timedelta) -> CollectionSchedule:
        return cls(interval=interval, next_collect_at=now + interval)
