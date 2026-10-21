from dataclasses import dataclass

from caramelo.domain.catalog import Listing
from caramelo.domain.ids import SourceId
from caramelo.domain.money import Price
from caramelo.domain.pricing import PricePoint


@dataclass(frozen=True, slots=True)
class RawOffer:
    """What a store integration yields, already normalized to domain types."""

    source_id: SourceId
    external_id: str
    url: str
    title: str
    pix: Price | None
    card: Price | None
    installments: int | None
    in_stock: bool
    seller: str | None = None
    mpn: str | None = None
    ean: str | None = None


@dataclass(frozen=True, slots=True)
class Deal:
    """A price point that passed the discount rules and may be published."""

    listing: Listing
    price: PricePoint
