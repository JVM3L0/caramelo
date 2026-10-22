from datetime import UTC, datetime, timedelta

import pytest

from caramelo.application.dashboard import HistoryPoint, ListingHistory, summarize
from caramelo.domain.ids import ListingId, SourceId, new_id
from caramelo.domain.money import Price

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def point(hours: int, pix: int | None, card: int | None = None, in_stock: bool = True):
    return HistoryPoint(
        T0 + timedelta(hours=hours),
        Price(pix) if pix is not None else None,
        Price(card) if card is not None else None,
        in_stock,
    )


def history(*points: HistoryPoint) -> ListingHistory:
    return ListingHistory(ListingId(new_id()), SourceId("kabum"), "Placa", "u", points)


def test_summarizes_the_pix_price_of_in_stock_collections() -> None:
    result = summarize(history(point(0, 20000), point(1, 18000), point(2, 22000), point(3, 19000)))

    assert (result.collections, result.in_stock_collections) == (4, 4)
    assert result.lowest == Price(18000)
    assert result.highest == Price(22000)
    assert result.median == Price(19500)  # between 19000 and 20000
    assert result.current == Price(19000)
    assert result.vs_median == pytest.approx(-500 / 19500)


def test_sold_out_collections_do_not_count_as_prices() -> None:
    result = summarize(history(point(0, 20000), point(1, None, None, False)))

    assert result.collections == 2 and result.in_stock_collections == 1
    assert result.lowest == result.highest == result.median == Price(20000)
    assert result.current is None  # the latest collection is sold out
    assert result.vs_median is None


def test_card_price_is_used_when_there_is_no_pix() -> None:
    result = summarize(history(point(0, None, 25000), point(1, None, 23000)))

    assert result.lowest == Price(23000)
    assert result.current == Price(23000)


def test_an_empty_history_has_nothing_to_summarize() -> None:
    result = summarize(history())

    assert result.collections == 0
    assert result.lowest is result.median is result.current is None
