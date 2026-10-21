from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True, order=True)
class Price:
    """Amount in BRL, stored as integer cents to avoid float rounding."""

    cents: int

    def __post_init__(self) -> None:
        if self.cents < 0:
            raise ValueError(f"price cannot be negative: {self.cents}")

    @classmethod
    def from_reais(cls, value: Decimal | str | int) -> Price:
        cents = Decimal(value) * 100
        if cents != cents.to_integral_value():
            raise ValueError(f"price has more than two decimal places: {value}")
        return cls(int(cents))

    def __str__(self) -> str:
        reais, cents = divmod(self.cents, 100)
        return f"R$ {reais:,}".replace(",", ".") + f",{cents:02d}"
