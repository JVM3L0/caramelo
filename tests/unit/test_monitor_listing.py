from datetime import timedelta

import pytest

from caramelo.application.use_cases.monitor_listing import (
    MonitorListing,
    ProductNotFound,
    UnknownStoreUrl,
)
from caramelo.domain.ids import SourceId
from tests.factories import raw_offer
from tests.fakes import FakeCatalog, FakeClock, FakePriceHistory, FakeSource, FakeUnitOfWork


def build() -> tuple[MonitorListing, FakeCatalog, FakePriceHistory]:
    catalog, prices = FakeCatalog(), FakePriceHistory()
    source = FakeSource("kabum", [raw_offer("123")])
    monitor = MonitorListing(
        {SourceId("kabum"): source}, lambda: FakeUnitOfWork(catalog, prices), FakeClock()
    )
    return monitor, catalog, prices


async def test_monitoring_collects_once_and_schedules_the_next_run() -> None:
    monitor, catalog, prices = build()

    result = await monitor("https://kabum.test/123", timedelta(minutes=30))

    assert result.first_price in prices.points
    assert result.listing.monitored
    (stored,) = catalog.listings.values()
    assert stored.schedule is not None
    assert stored.schedule.interval == timedelta(minutes=30)
    assert stored.schedule.next_collect_at == prices.points[0].collected_at + timedelta(minutes=30)


async def test_unknown_store_url_is_rejected() -> None:
    monitor, catalog, _ = build()

    with pytest.raises(UnknownStoreUrl):
        await monitor("https://outra-loja.test/1", timedelta(hours=1))
    assert not catalog.listings


async def test_product_missing_in_store_is_not_saved() -> None:
    monitor, catalog, _ = build()

    with pytest.raises(ProductNotFound):
        await monitor("https://kabum.test/999", timedelta(hours=1))
    assert not catalog.listings
