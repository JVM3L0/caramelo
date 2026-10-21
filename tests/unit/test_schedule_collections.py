from datetime import UTC, datetime, timedelta

from caramelo.application import jobs
from caramelo.application.use_cases.schedule_collections import ScheduleDueCollections
from caramelo.domain.catalog import CollectionSchedule
from tests.factories import raw_offer
from tests.fakes import FakeCatalog, FakeClock, FakePriceHistory, FakeTaskQueue, FakeUnitOfWork

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


async def seed(
    catalog: FakeCatalog, source: str, external_id: str, next_at: datetime | None
) -> None:
    listing = await catalog.upsert_listing(raw_offer(external_id, source_id=source), seen_at=NOW)
    schedule = CollectionSchedule(timedelta(hours=1), next_at) if next_at else None
    await catalog.set_schedule(listing.id, schedule)


def build(catalog: FakeCatalog, queue: FakeTaskQueue, batch_size: int = 20):
    uow = FakeUnitOfWork(catalog, FakePriceHistory())
    clock = FakeClock(NOW, step=timedelta(0))
    return ScheduleDueCollections(lambda: uow, queue, clock, batch_size=batch_size)


async def test_enqueues_only_due_monitored_listings_per_store() -> None:
    catalog, queue = FakeCatalog(), FakeTaskQueue()
    await seed(catalog, "kabum", "a", NOW - timedelta(minutes=1))
    await seed(catalog, "kabum", "b", NOW)
    await seed(catalog, "kabum", "later", NOW + timedelta(minutes=5))
    await seed(catalog, "kabum", "unmonitored", None)
    await seed(catalog, "mercadolivre", "x", NOW - timedelta(hours=2))

    claimed = await build(catalog, queue)()

    assert claimed == 3
    by_store = {payload["source_id"]: payload["external_ids"] for _, _, payload in queue.jobs}
    assert sorted(by_store["kabum"]) == ["a", "b"]  # type: ignore[arg-type]
    assert by_store["mercadolivre"] == ["x"]
    assert {(job, lock) for job, lock, _ in queue.jobs} == {
        (jobs.COLLECT_LISTINGS, "source:kabum"),
        (jobs.COLLECT_LISTINGS, "source:mercadolivre"),
    }


async def test_claimed_listings_move_to_their_next_slot() -> None:
    catalog, queue = FakeCatalog(), FakeTaskQueue()
    await seed(catalog, "kabum", "a", NOW - timedelta(hours=5))
    scheduler = build(catalog, queue)

    assert await scheduler() == 1
    assert await scheduler() == 0  # not claimed twice, and no catch-up burst
    (listing,) = catalog.listings.values()
    assert listing.schedule is not None
    assert listing.schedule.next_collect_at == NOW + timedelta(hours=1)


async def test_large_batches_are_split() -> None:
    catalog, queue = FakeCatalog(), FakeTaskQueue()
    for i in range(5):
        await seed(catalog, "kabum", str(i), NOW - timedelta(minutes=i))

    await build(catalog, queue, batch_size=2)()

    assert sorted(len(payload["external_ids"]) for _, _, payload in queue.jobs) == [1, 2, 2]  # type: ignore[arg-type]
