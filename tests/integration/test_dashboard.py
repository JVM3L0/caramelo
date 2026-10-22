"""The dashboard queries against a real TimescaleDB, with data whose answers are known."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from caramelo.adapters.persistence import to_sqlalchemy_url
from caramelo.adapters.persistence.dashboard import SqlDashboardQueries
from caramelo.adapters.persistence.repositories import SqlUnitOfWork
from caramelo.adapters.queue import procrastinate as queue
from caramelo.adapters.queue.stats import ProcrastinateQueueStatistics
from caramelo.application import jobs
from caramelo.application.dashboard import ListingQuery
from caramelo.domain.catalog import CollectionSchedule
from caramelo.domain.ids import SourceId
from caramelo.domain.money import Price
from caramelo.domain.pricing import PricePoint
from tests.factories import raw_offer

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
H = timedelta(hours=1)
MIN = timedelta(minutes=1)


async def _add(
    engine: AsyncEngine,
    external_id: str,
    title: str,
    points: list[tuple[datetime, int | None, bool]],
    schedule: CollectionSchedule | None = None,
) -> None:
    async with SqlUnitOfWork(engine) as uow:
        listing = await uow.catalog.upsert_listing(
            raw_offer(external_id, title=title, source_id=SourceId("dash")), seen_at=NOW
        )
        for at, pix, in_stock in points:
            price = Price(pix) if pix is not None else None
            await uow.prices.append(PricePoint(listing.id, at, price, price, 10, in_stock))
        if schedule:
            await uow.catalog.set_schedule(listing.id, schedule)
        await uow.commit()


async def _seed(url: str) -> None:
    engine = create_async_engine(to_sqlalchemy_url(url))
    try:
        # a: monitored hourly, overdue, got 10% cheaper
        await _add(
            engine,
            "a",
            "RTX 4070 Ti Ventus",
            [(NOW - 2 * H, 20000, True), (NOW - H, 18000, True)],
            CollectionSchedule(H, NOW - 30 * MIN),
        )
        # b: monitored every 2 h, now sold out, title with LIKE wildcards
        await _add(
            engine,
            "b",
            "SSD Kingston 1TB 50%_off",
            [(NOW - 3 * H, 30000, True), (NOW - 30 * MIN, None, False)],
            CollectionSchedule(2 * H, NOW + H),
        )
        # c: not monitored
        await _add(engine, "c", "Cabo HDMI", [(NOW - 10 * MIN, 5000, True)])
        # d: monitored every 30 min, 10% more expensive
        await _add(
            engine,
            "d",
            "RTX 4070 SUPER Windforce",
            [(NOW - 2 * H, 10000, True), (NOW - 30 * MIN, 11000, True)],
            CollectionSchedule(30 * MIN, NOW + 10 * MIN),
        )
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def seeded(database_url: str) -> Iterator[str]:
    asyncio.run(_seed(database_url))
    yield database_url


async def _ids(queries: SqlDashboardQueries, **query: object) -> list[str]:
    return [r.external_id for r in await queries.listings(ListingQuery(**query))]  # type: ignore[arg-type]


async def test_source_health_summarizes_the_collection(seeded: str, engine: AsyncEngine) -> None:
    (health,) = await SqlDashboardQueries(engine).source_health(NOW)

    assert health.source_id == "dash"
    assert health.monitored == 3  # a, b and d; c is not monitored
    assert health.sold_out == 1  # b
    assert health.overdue == 1  # a is 30 min late, the grace period is 10 min
    assert health.price_points == 7
    assert health.points_last_hour == 3  # b, c and d; a's latest is exactly one hour old
    assert health.last_collected_at == NOW - 10 * MIN
    assert health.next_collect_at == NOW - 30 * MIN
    assert health.estimated_requests_per_hour == pytest.approx(3.5)  # 1 + 0.5 + 2


async def test_listings_carry_the_latest_prices_and_the_change(
    seeded: str, engine: AsyncEngine
) -> None:
    rows = {r.external_id: r for r in await SqlDashboardQueries(engine).listings(ListingQuery())}

    assert rows["a"].pix == Price(18000)
    assert rows["a"].points == 2
    assert rows["a"].change == pytest.approx(-0.1)
    assert rows["d"].change == pytest.approx(0.1)
    assert rows["b"].pix is None and not rows["b"].in_stock
    assert rows["b"].change is None  # sold out: there is no new price to compare
    assert rows["c"].change is None  # a single collection so far
    assert rows["c"].next_collect_at is None


async def test_orderings(seeded: str, engine: AsyncEngine) -> None:
    queries = SqlDashboardQueries(engine)

    assert await _ids(queries, order="recent") == ["c", "d", "b", "a"]
    assert await _ids(queries, order="price") == ["c", "d", "a", "b"]
    assert await _ids(queries, order="change") == ["a", "d", "c", "b"]
    assert await _ids(queries, order="title") == ["c", "d", "a", "b"]


async def test_filters(seeded: str, engine: AsyncEngine) -> None:
    queries = SqlDashboardQueries(engine)

    assert sorted(await _ids(queries, in_stock=True)) == ["a", "c", "d"]
    assert await _ids(queries, in_stock=False) == ["b"]
    # only real price changes: sold-out and single-collection listings are not changes
    assert sorted(await _ids(queries, changed_only=True)) == ["a", "d"]
    assert len(await _ids(queries, limit=2)) == 2


async def test_search_is_case_insensitive_and_wildcards_are_literal(
    seeded: str, engine: AsyncEngine
) -> None:
    queries = SqlDashboardQueries(engine)

    assert await _ids(queries, search="VENTUS") == ["a"]
    assert sorted(await _ids(queries, search="rtx 4070")) == ["a", "d"]
    assert await _ids(queries, search="50%") == ["b"]
    assert await _ids(queries, search="%") == ["b"]  # not "match everything"
    assert await _ids(queries, search="_") == ["b"]
    assert await _ids(queries, search="nothing like this") == []


async def test_queue_statistics(seeded: str) -> None:
    async def handler(**_: object) -> None:
        return None

    app = queue.create_app(seeded)
    queue.register(app, {jobs.COLLECT_LISTINGS: handler})
    async with app.open_async():
        await queue.ensure_schema(app)
        stats = ProcrastinateQueueStatistics(app)
        assert (await stats.stats()).pending == 0

        await queue.ProcrastinateTaskQueue(app).enqueue(
            jobs.COLLECT_LISTINGS, source_id="dash", external_ids=["a"]
        )
        result = await stats.stats()

    assert (result.pending, result.running, result.failed) == (1, 0, 0)
    assert result.oldest_pending_at is not None


async def _listing_ids(queries: SqlDashboardQueries) -> dict:
    return {r.external_id: r.listing_id for r in await queries.listings(ListingQuery())}


async def test_trend_holds_the_recent_prices_oldest_first(seeded: str, engine: AsyncEngine) -> None:
    rows = {r.external_id: r for r in await SqlDashboardQueries(engine).listings(ListingQuery())}

    assert rows["a"].trend == (20000, 18000)
    assert rows["d"].trend == (10000, 11000)
    assert rows["b"].trend == (30000,)  # the sold-out collection has no price to draw
    assert rows["c"].trend == (5000,)


async def test_history_returns_the_collections_oldest_first(
    seeded: str, engine: AsyncEngine
) -> None:
    queries = SqlDashboardQueries(engine)
    ids = await _listing_ids(queries)

    history = await queries.history(ids["a"], NOW - 7 * 24 * H)

    assert history is not None
    assert (history.source_id, history.title) == ("dash", "RTX 4070 Ti Ventus")
    assert [p.pix for p in history.points] == [Price(20000), Price(18000)]
    assert [p.collected_at for p in history.points] == [NOW - 2 * H, NOW - H]


async def test_history_includes_sold_out_collections(seeded: str, engine: AsyncEngine) -> None:
    queries = SqlDashboardQueries(engine)
    ids = await _listing_ids(queries)

    history = await queries.history(ids["b"], NOW - 7 * 24 * H)

    assert history is not None
    assert [(p.pix, p.in_stock) for p in history.points] == [(Price(30000), True), (None, False)]


async def test_history_respects_since_and_keeps_the_newest_when_limited(
    seeded: str, engine: AsyncEngine
) -> None:
    queries = SqlDashboardQueries(engine)
    ids = await _listing_ids(queries)

    recent = await queries.history(ids["a"], NOW - 90 * MIN)
    limited = await queries.history(ids["a"], NOW - 7 * 24 * H, limit=1)

    assert recent is not None and [p.pix for p in recent.points] == [Price(18000)]
    assert limited is not None and [p.pix for p in limited.points] == [Price(18000)]


async def test_history_of_an_unknown_listing_is_none(seeded: str, engine: AsyncEngine) -> None:
    from caramelo.domain.ids import ListingId, new_id

    assert await SqlDashboardQueries(engine).history(ListingId(new_id()), NOW - H) is None


async def test_activity_has_one_bucket_per_hour_including_empty_ones(
    seeded: str, engine: AsyncEngine
) -> None:
    buckets = await SqlDashboardQueries(engine).activity(NOW, hours=6)

    assert [b.hour.astimezone(UTC).hour for b in buckets] == [7, 8, 9, 10, 11, 12]
    assert [b.points for b in buckets] == [0, 0, 1, 2, 4, 0]
