from datetime import timedelta

from caramelo.application.use_cases.seed_catalog import SeedCatalog
from tests.factories import raw_offer
from tests.fakes import FakeCatalog, FakeClock, FakePriceHistory, FakeSource, FakeUnitOfWork

HOUR = timedelta(hours=1)


def build(offers: list, catalog: FakeCatalog | None = None):
    catalog = catalog or FakeCatalog()
    prices = FakePriceHistory()
    clock = FakeClock(step=timedelta(0))
    source = FakeSource("kabum", [], categories={"hardware/ssd": offers})
    seed = SeedCatalog(lambda: FakeUnitOfWork(catalog, prices), clock)
    return seed, source, catalog, prices, clock


async def test_monitors_every_discovered_product_and_records_its_first_price() -> None:
    seed, source, catalog, prices, _ = build([raw_offer("1"), raw_offer("2"), raw_offer("3")])

    result = await seed(source, "hardware/ssd", 2, 2 * HOUR)

    assert (result.discovered, result.newly_monitored, result.already_monitored) == (3, 3, 0)
    assert source.discovered == [("hardware/ssd", 2)]
    assert all(listing.monitored for listing in catalog.listings.values())
    assert len(prices.points) == 3  # prices came with the discovery, no extra request


async def test_first_collections_are_spread_across_the_interval() -> None:
    seed, source, catalog, _, clock = build([raw_offer(str(n)) for n in range(4)])
    start = clock.now()

    await seed(source, "hardware/ssd", 1, 2 * HOUR)

    due = sorted(
        item.schedule.next_collect_at - start for item in catalog.listings.values() if item.schedule
    )
    assert due == [30 * timedelta(minutes=1) * k for k in (1, 2, 3, 4)]


async def test_products_already_monitored_keep_their_schedule() -> None:
    catalog = FakeCatalog()
    seed, source, _, prices, _ = build([raw_offer("1"), raw_offer("2")], catalog)
    await seed(source, "hardware/ssd", 1, HOUR)
    original = {key: listing.schedule for key, listing in catalog.listings.items()}

    result = await seed(source, "hardware/ssd", 1, 6 * HOUR)

    assert (result.newly_monitored, result.already_monitored) == (0, 2)
    assert {key: listing.schedule for key, listing in catalog.listings.items()} == original
    assert len(prices.points) == 4  # but the fresh prices are still recorded


async def test_empty_category_changes_nothing() -> None:
    seed, source, catalog, prices, _ = build([])

    result = await seed(source, "hardware/ssd", 1, HOUR)

    assert result.discovered == 0
    assert not catalog.listings
    assert not prices.points
