from caramelo.application.use_cases.collect_listings import CollectListings
from tests.factories import raw_offer
from tests.fakes import FakeCatalog, FakeClock, FakePriceHistory, FakeSource, FakeUnitOfWork


async def test_records_every_requested_offer_in_price_history() -> None:
    catalog, prices = FakeCatalog(), FakePriceHistory()
    uow = FakeUnitOfWork(catalog, prices)
    collect = CollectListings(lambda: uow, FakeClock())
    source = FakeSource("kabum", [raw_offer("1"), raw_offer("2", pix=None), raw_offer("3")])

    recorded = await collect(source, ["1", "2"])

    assert recorded == 2
    assert uow.commits == 2
    assert {key[1] for key in catalog.listings} == {"1", "2"}
    assert [p.pix for p in prices.points] == [raw_offer().pix, None]


async def test_products_the_store_no_longer_returns_are_skipped() -> None:
    catalog, prices = FakeCatalog(), FakePriceHistory()
    collect = CollectListings(lambda: FakeUnitOfWork(catalog, prices), FakeClock())

    recorded = await collect(FakeSource("kabum", [raw_offer("1")]), ["1", "gone"])

    assert recorded == 1


async def test_same_listing_accumulates_history() -> None:
    catalog, prices = FakeCatalog(), FakePriceHistory()
    collect = CollectListings(lambda: FakeUnitOfWork(catalog, prices), FakeClock())

    await collect(FakeSource("kabum", [raw_offer("1")]), ["1"])
    await collect(FakeSource("kabum", [raw_offer("1", title="Novo título")]), ["1"])

    (listing,) = catalog.listings.values()
    assert listing.title == "Novo título"
    assert {p.listing_id for p in prices.points} == {listing.id}
    assert prices.points[0].collected_at < prices.points[1].collected_at
