from dataclasses import dataclass
from datetime import datetime

from caramelo.domain.ids import ListingId
from caramelo.domain.money import Price


@dataclass(frozen=True, slots=True)
class PricePoint:
    """One observation of a listing's price.

    Pix and card prices are kept apart: hardware stores show both and comparing
    across them produces fake discounts.
    """

    listing_id: ListingId
    collected_at: datetime
    pix: Price | None
    card: Price | None
    installments: int | None
    in_stock: bool

    def __post_init__(self) -> None:
        if self.collected_at.tzinfo is None:
            raise ValueError("collected_at must be timezone-aware")
        if self.installments is not None and self.installments < 1:
            raise ValueError(f"installments must be >= 1: {self.installments}")
        if self.in_stock and self.pix is None and self.card is None:
            raise ValueError("an in-stock price point needs at least one price")

    @property
    def best(self) -> Price | None:
        prices = [p for p in (self.pix, self.card) if p is not None]
        return min(prices, default=None)
