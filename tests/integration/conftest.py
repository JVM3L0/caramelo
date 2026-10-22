from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from caramelo.adapters.persistence import migrate, to_sqlalchemy_url

TIMESCALE_IMAGE = "docker.io/timescale/timescaledb:2.17.2-pg16"


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    """A migrated TimescaleDB, one per test module so modules never see each other's data."""
    with PostgresContainer(TIMESCALE_IMAGE, driver=None) as pg:
        url = pg.get_connection_url()
        migrate.upgrade(to_sqlalchemy_url(url))
        yield url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(to_sqlalchemy_url(database_url))
    yield engine
    await engine.dispose()
