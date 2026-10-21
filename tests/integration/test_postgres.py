"""Runs migrations against a real TimescaleDB container and exercises the SQL adapters."""

from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from caramelo.adapters.persistence import migrate, to_sqlalchemy_url
from caramelo.adapters.persistence.repositories import SqlUnitOfWork
from caramelo.adapters.persistence.tables import listings, price_points
from caramelo.adapters.queue import procrastinate as queue
from caramelo.application import jobs
from caramelo.application.use_cases.collect_listings import CollectListings
from caramelo.application.use_cases.schedule_collections import ScheduleDueCollections
from caramelo.domain.catalog import CollectionSchedule
from tests.factories import raw_offer
from tests.fakes import FakeClock, FakeSource

pytestmark = pytest.mark.integration

TIMESCALE_IMAGE = "docker.io/timescale/timescaledb:2.17.2-pg16"


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer(TIMESCALE_IMAGE, driver=None) as pg:
        url = pg.get_connection_url()
        migrate.upgrade(to_sqlalchemy_url(url))
        yield url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(to_sqlalchemy_url(database_url))
    yield engine
    await engine.dispose()


async def test_price_points_is_a_hypertable(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = :t"),
            {"t": "price_points"},
        )
        assert result.scalar_one() == 1


async def test_collect_listings_persists_listings_and_history(engine: AsyncEngine) -> None:
    collect = CollectListings(lambda: SqlUnitOfWork(engine), FakeClock())

    await collect(FakeSource("kabum", [raw_offer("a"), raw_offer("b")]), ["a", "b"])
    await collect(FakeSource("kabum", [raw_offer("a", title="Atualizado")]), ["a"])

    async with engine.connect() as conn:
        titles = dict((await conn.execute(select(listings.c.external_id, listings.c.title))).all())
        points = (await conn.execute(select(func.count()).select_from(price_points))).scalar_one()
    assert titles == {"a": "Atualizado", "b": raw_offer().title}
    assert points == 3


async def test_uncommitted_work_is_rolled_back(engine: AsyncEngine) -> None:
    async with SqlUnitOfWork(engine) as uow:
        await uow.catalog.upsert_listing(raw_offer("rollback"), seen_at=FakeClock().now())

    async with engine.connect() as conn:
        found = await conn.execute(
            select(listings.c.id).where(listings.c.external_id == "rollback")
        )
        assert found.first() is None


async def test_queue_schema_is_applied_idempotently(database_url: str) -> None:
    app = queue.create_app(database_url)
    async with app.open_async():
        await queue.ensure_schema(app)
        await queue.ensure_schema(app)
        row = await app.connector.execute_query_one_async(
            "SELECT to_regclass('procrastinate_jobs') IS NOT NULL AS present"
        )
    assert row["present"]


async def test_claim_due_moves_listings_and_skips_locked_rows(engine: AsyncEngine) -> None:
    clock = FakeClock(step=timedelta(0))
    now = clock.now()
    interval = timedelta(hours=1)
    async with SqlUnitOfWork(engine) as uow:
        for name, next_at in [("due1", now - interval), ("due2", now), ("later", now + interval)]:
            listing = await uow.catalog.upsert_listing(raw_offer(name), seen_at=now)
            await uow.catalog.set_schedule(listing.id, CollectionSchedule(interval, next_at))
        await uow.commit()

    # A concurrent scheduler holding one row must not make the other claim it twice.
    async with SqlUnitOfWork(engine) as first, SqlUnitOfWork(engine) as second:
        claimed_first = await first.catalog.claim_due(now, limit=1)
        claimed_second = await second.catalog.claim_due(now, limit=10)
        assert len(claimed_first) == 1
        assert len(claimed_second) == 1
        assert {claimed_first[0].external_id, claimed_second[0].external_id} == {"due1", "due2"}
        assert claimed_first[0].schedule == CollectionSchedule(interval, now + interval)
        await first.commit()
        await second.commit()

    async with SqlUnitOfWork(engine) as uow:
        assert await uow.catalog.claim_due(now, limit=10) == []


async def test_scheduler_enqueues_jobs_in_postgres(engine: AsyncEngine, database_url: str) -> None:
    clock = FakeClock(step=timedelta(0))
    now = clock.now()
    async with SqlUnitOfWork(engine) as uow:
        listing = await uow.catalog.upsert_listing(raw_offer("sched"), seen_at=now)
        schedule = CollectionSchedule(timedelta(hours=1), now - timedelta(minutes=1))
        await uow.catalog.set_schedule(listing.id, schedule)
        await uow.commit()

    app = queue.create_app(database_url)
    queue.register(app, {jobs.COLLECT_LISTINGS: _noop}, periodic={})
    async with app.open_async():
        await queue.ensure_schema(app)
        scheduler = ScheduleDueCollections(
            lambda: SqlUnitOfWork(engine), queue.ProcrastinateTaskQueue(app), clock
        )
        assert await scheduler() == 1
        row = await app.connector.execute_query_one_async(
            "SELECT lock, args FROM procrastinate_jobs WHERE task_name = %(name)s",
            name=jobs.COLLECT_LISTINGS,
        )
    assert row["lock"] == "source:kabum"
    assert row["args"] == {"source_id": "kabum", "external_ids": ["sched"]}


async def _noop(**_: object) -> None:
    return None
