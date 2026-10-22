import re
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from caramelo.adapters.persistence import migrate, to_sqlalchemy_url

TIMESCALE_IMAGE = "docker.io/timescale/timescaledb:2.17.2-pg16"


@pytest.fixture(scope="session")
def timescale_url() -> Iterator[str]:
    """One TimescaleDB container for the whole run: pulling and starting it is the slow part."""
    with PostgresContainer(TIMESCALE_IMAGE, driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="module")
def database_url(timescale_url: str, request: pytest.FixtureRequest) -> str:
    """A migrated database of its own for each test module, so modules never see each
    other's data even though they share the container."""
    name = "t_" + re.sub(r"\W+", "_", request.module.__name__.rsplit(".", 1)[-1])
    admin = create_engine(to_sqlalchemy_url(timescale_url), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    url = make_url(timescale_url).set(database=name).render_as_string(hide_password=False)
    migrate.upgrade(to_sqlalchemy_url(url))
    return url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(to_sqlalchemy_url(database_url))
    yield engine
    await engine.dispose()
