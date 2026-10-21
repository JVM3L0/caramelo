from datetime import datetime
from types import TracebackType
from typing import Self

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from caramelo.adapters.persistence.tables import listings, price_points
from caramelo.domain.catalog import Listing
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
        row = (await self._conn.execute(stmt)).one()
        return Listing(
            id=ListingId(row.id),
            source_id=SourceId(row.source_id),
            external_id=row.external_id,
            url=row.url,
            title=row.title,
            product_id=ProductId(row.product_id) if row.product_id else None,
            monitored=row.monitored,
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
