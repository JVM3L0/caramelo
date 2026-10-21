from datetime import UTC, datetime

import pytest

from caramelo.domain.ids import ListingId, new_id
from caramelo.domain.money import Price
from caramelo.domain.pricing import PricePoint


class TestPrice:
    def test_formats_as_brazilian_reais(self) -> None:
        assert str(Price.from_reais("4199.90")) == "R$ 4.199,90"
        assert str(Price(5)) == "R$ 0,05"
        assert str(Price.from_reais(1234567)) == "R$ 1.234.567,00"

    def test_rejects_fractions_of_a_cent(self) -> None:
        with pytest.raises(ValueError, match="two decimal places"):
            Price.from_reais("10.001")

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            Price(-1)


def point(**overrides: object) -> PricePoint:
    fields: dict[str, object] = {
        "listing_id": ListingId(new_id()),
        "collected_at": datetime(2026, 10, 21, tzinfo=UTC),
        "pix": Price(100_00),
        "card": Price(110_00),
        "installments": 10,
        "in_stock": True,
    }
    fields.update(overrides)
    return PricePoint(**fields)  # type: ignore[arg-type]


class TestPricePoint:
    def test_best_is_lowest_available_price(self) -> None:
        assert point().best == Price(100_00)
        assert point(pix=None).best == Price(110_00)

    def test_requires_timezone(self) -> None:
        with pytest.raises(ValueError, match="timezone"):
            point(collected_at=datetime(2026, 10, 21))

    def test_in_stock_needs_a_price(self) -> None:
        with pytest.raises(ValueError, match="at least one price"):
            point(pix=None, card=None)

    def test_out_of_stock_may_have_no_price(self) -> None:
        assert point(pix=None, card=None, in_stock=False).best is None
