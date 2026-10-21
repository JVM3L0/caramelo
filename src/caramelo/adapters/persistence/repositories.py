from datetime import datetime
from types import TracebackType
from typing import Any, Self

from sqlalchemy import DateTime, Row, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from caramelo.adapters.persistence.tables import listings, price_points
from caramelo.domain.catalog import CollectionSchedule, Listing
from caramelo.domain.ids import ListingId, ProductId, SourceId, new_id
from caramelo.domain.offers import RawOffer
from caramelo.domain.pricing import PricePoint


class SqlCatalogRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def upsert_listing(self, offer: RawOffer, seen_at: datetime) -> Listing:
        stmt = insert(listings).values(
            id=new_id(),
            source_id=offer.source_id,
            external_id=offer.external_id,
            url=offer.url,
            title=offer.title,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[listings.c.source_id, listings.c.external_id],
            set_={
                "url": stmt.excluded.url,
                "title": stmt.excluded.title,
                "last_seen_at": stmt.excluded.last_seen_at,
            },
        ).returning(listings)
        return _to_listing((await self._conn.execute(stmt)).one())

    async def set_schedule(
        self, listing_id: ListingId, schedule: CollectionSchedule | None
    ) -> None:
        await self._conn.execute(
            update(listings)
            .where(listings.c.id == listing_id)
            .values(
                collect_interval=schedule.interval if schedule else None,
                next_collect_at=schedule.next_collect_at if schedule else None,
            )
        )

    async def claim_due(self, now: datetime, limit: int) -> list[Listing]:
        due = (
            select(listings.c.id)
            .where(listings.c.next_collect_at <= now)
            .order_by(listings.c.next_collect_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        # Next slot counts from now, so a worker that was down doesn't cause a burst.
        stmt = (
            update(listings)
            .where(listings.c.id.in_(due))
            .values(
                next_collect_at=literal(now, DateTime(timezone=True)) + listings.c.collect_interval
            )
            .returning(listings)
        )
        return [_to_listing(row) for row in await self._conn.execute(stmt)]


def _to_listing(row: Row[Any]) -> Listing:
    return Listing(
        id=ListingId(row.id),
        source_id=SourceId(row.source_id),
        external_id=row.external_id,
        url=row.url,
        title=row.title,
        product_id=ProductId(row.product_id) if row.product_id else None,
        schedule=CollectionSchedule(row.collect_interval, row.next_collect_at)
        if row.collect_interval is not None
        else None,
    )


class SqlPriceHistory:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def append(self, point: PricePoint) -> None:
        stmt = (
            insert(price_points)
            .values(
                listing_id=point.listing_id,
                collected_at=point.collected_at,
                pix_cents=point.pix.cents if point.pix else None,
                card_cents=point.card.cents if point.card else None,
                installments=point.installments,
                in_stock=point.in_stock,
            )
            .on_conflict_do_nothing()
        )
        await self._conn.execute(stmt)


class SqlUnitOfWork:
    catalog: SqlCatalogRepository
    prices: SqlPriceHistory

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._conn: AsyncConnection | None = None

    async def __aenter__(self) -> Self:
        self._conn = await self._engine.connect()
        await self._conn.begin()
        self.catalog = SqlCatalogRepository(self._conn)
        self.prices = SqlPriceHistory(self._conn)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._conn is not None
        # No-op when commit() already ended the transaction.
        await self._conn.rollback()
        await self._conn.close()
        self._conn = None

    async def commit(self) -> None:
        assert self._conn is not None
        await self._conn.commit()
