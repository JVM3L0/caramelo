from caramelo.application.use_cases.collect_source import CollectSource
from tests.factories import raw_offer
from tests.fakes import FakeCatalog, FakeClock, FakePriceHistory, FakeSource, FakeUnitOfWork


async def test_records_every_offer_in_price_history() -> None:
    catalog, prices = FakeCatalog(), FakePriceHistory()
    uow = FakeUnitOfWork(catalog, prices)
    collect = CollectSource(lambda: uow, FakeClock())

    source = FakeSource("kabum", [raw_offer("1"), raw_offer("2", pix=None)])
    recorded = await collect(source)

    assert recorded == 2
    assert uow.commits == 2
    assert len(catalog.listings) == 2
    assert [p.pix for p in prices.points] == [raw_offer().pix, None]


async def test_same_listing_accumulates_history() -> None:
    catalog, prices = FakeCatalog(), FakePriceHistory()
    collect = CollectSource(lambda: FakeUnitOfWork(catalog, prices), FakeClock())

    await collect(FakeSource("kabum", [raw_offer("1")]))
    await collect(FakeSource("kabum", [raw_offer("1", title="Novo título")]))

    (listing,) = catalog.listings.values()
    assert listing.title == "Novo título"
    assert {p.listing_id for p in prices.points} == {listing.id}
    assert prices.points[0].collected_at < prices.points[1].collected_at
