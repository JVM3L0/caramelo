"""Runs migrations against a real TimescaleDB container and exercises the SQL adapters."""

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from caramelo.adapters.persistence import migrate, to_sqlalchemy_url
from caramelo.adapters.persistence.repositories import SqlUnitOfWork
from caramelo.adapters.persistence.tables import listings, price_points
from caramelo.adapters.queue import procrastinate as queue
from caramelo.application.use_cases.collect_source import CollectSource
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


async def test_collect_source_persists_listings_and_history(engine: AsyncEngine) -> None:
    collect = CollectSource(lambda: SqlUnitOfWork(engine), FakeClock())

    await collect(FakeSource("kabum", [raw_offer("a"), raw_offer("b")]))
    await collect(FakeSource("kabum", [raw_offer("a", title="Atualizado")]))

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
    app = queue.build_app(database_url, handlers={})
    async with app.open_async():
        await queue.ensure_schema(app)
        await queue.ensure_schema(app)
        row = await app.connector.execute_query_one_async(
            "SELECT to_regclass('procrastinate_jobs') IS NOT NULL AS present"
        )
    assert row["present"]
