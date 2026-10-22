from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Boolean, Integer, String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine

from caramelo.application.dashboard import (
    ActivityBucket,
    HistoryPoint,
    ListingHistory,
    ListingOrder,
    ListingQuery,
    ListingRow,
    SourceHealth,
)
from caramelo.domain.ids import ListingId, SourceId
from caramelo.domain.money import Price

# Whitelist: the order is chosen by key, never interpolated from user input.
_ORDER_SQL: dict[ListingOrder, str] = {
    "recent": "collected_at DESC",
    "price": "cur ASC NULLS LAST",
    "change": "chg ASC NULLS LAST",
    "title": "lower(title) ASC",
}

_LISTINGS_SQL = """
WITH rows AS (
    SELECT l.id, l.source_id, l.external_id, l.title, l.url, l.next_collect_at,
           p.pix_cents, p.card_cents, p.in_stock, p.collected_at, c.points,
           COALESCE(p.pix_cents, p.card_cents) AS cur,
           COALESCE(prev.pix_cents, prev.card_cents) AS prv,
           tr.trend
    FROM listings l
    JOIN LATERAL (
        SELECT pix_cents, card_cents, in_stock, collected_at FROM price_points
        WHERE listing_id = l.id ORDER BY collected_at DESC LIMIT 1
    ) p ON true
    JOIN LATERAL (
        SELECT count(*) AS points FROM price_points WHERE listing_id = l.id
    ) c ON true
    LEFT JOIN LATERAL (
        SELECT pix_cents, card_cents FROM price_points
        WHERE listing_id = l.id AND collected_at < p.collected_at
        ORDER BY collected_at DESC LIMIT 1
    ) prev ON true
    LEFT JOIN LATERAL (
        SELECT array_agg(v ORDER BY ts) AS trend FROM (
            SELECT COALESCE(pix_cents, card_cents) AS v, collected_at AS ts FROM price_points
            WHERE listing_id = l.id ORDER BY collected_at DESC LIMIT 12
        ) recent WHERE v IS NOT NULL
    ) tr ON true
    WHERE (CAST(:search AS text) = '' OR l.title ILIKE :pattern ESCAPE '\\')
      AND (CAST(:in_stock AS boolean) IS NULL OR p.in_stock = CAST(:in_stock AS boolean))
), scored AS (
    SELECT *, CASE WHEN prv > 0 AND cur IS NOT NULL
                   THEN (cur - prv)::float / prv END AS chg
    FROM rows
)
SELECT * FROM scored
WHERE (NOT CAST(:changed_only AS boolean) OR (cur IS NOT NULL AND prv IS NOT NULL AND cur <> prv))
ORDER BY {order}, title
LIMIT :limit
"""

_HEALTH_SQL = """
SELECT l.source_id,
       count(*) FILTER (WHERE l.next_collect_at IS NOT NULL) AS monitored,
       count(*) FILTER (WHERE p.in_stock IS FALSE) AS sold_out,
       count(*) FILTER (
           WHERE l.next_collect_at IS NOT NULL AND l.next_collect_at < :late_before
       ) AS overdue,
       max(p.collected_at) AS last_collected_at,
       min(l.next_collect_at) AS next_collect_at,
       COALESCE(sum(3600.0 / extract(epoch FROM l.collect_interval))
                FILTER (WHERE l.collect_interval IS NOT NULL), 0) AS requests_per_hour
FROM listings l
LEFT JOIN LATERAL (
    SELECT in_stock, collected_at FROM price_points
    WHERE listing_id = l.id ORDER BY collected_at DESC LIMIT 1
) p ON true
GROUP BY l.source_id
"""

_HISTORY_SQL = """
SELECT collected_at, pix_cents, card_cents, in_stock FROM (
    SELECT collected_at, pix_cents, card_cents, in_stock FROM price_points
    WHERE listing_id = :listing_id AND collected_at >= :since
    ORDER BY collected_at DESC LIMIT :limit
) newest ORDER BY collected_at
"""

_ACTIVITY_SQL = """
SELECT h AS hour, count(pp.listing_id) AS points
FROM generate_series(
    date_trunc('hour', CAST(:now AS timestamptz))
        - (CAST(:hours AS integer) - 1) * interval '1 hour',
    date_trunc('hour', CAST(:now AS timestamptz)),
    interval '1 hour'
) AS h
LEFT JOIN price_points pp ON pp.collected_at >= h AND pp.collected_at < h + interval '1 hour'
GROUP BY h ORDER BY h
"""

_POINTS_SQL = """
SELECT l.source_id, count(*) AS points,
       count(*) FILTER (WHERE pp.collected_at > :since) AS recent
FROM price_points pp JOIN listings l ON l.id = pp.listing_id
GROUP BY l.source_id
"""


def _like_pattern(search: str) -> str:
    """Escapes LIKE wildcards so a search for '50%' means exactly that."""
    escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _price(cents: int | None) -> Price | None:
    return Price(cents) if cents is not None else None


class SqlDashboardQueries:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def source_health(
        self, now: datetime, overdue_after: timedelta = timedelta(minutes=10)
    ) -> list[SourceHealth]:
        async with self._engine.connect() as conn:
            health = (
                await conn.execute(text(_HEALTH_SQL), {"late_before": now - overdue_after})
            ).all()
            points = {
                row.source_id: row
                for row in await conn.execute(
                    text(_POINTS_SQL), {"since": now - timedelta(hours=1)}
                )
            }
        return [
            SourceHealth(
                source_id=SourceId(row.source_id),
                monitored=row.monitored,
                sold_out=row.sold_out,
                price_points=points[row.source_id].points if row.source_id in points else 0,
                points_last_hour=points[row.source_id].recent if row.source_id in points else 0,
                last_collected_at=row.last_collected_at,
                next_collect_at=row.next_collect_at,
                overdue=row.overdue,
                estimated_requests_per_hour=float(row.requests_per_hour),
            )
            for row in health
        ]

    async def listings(self, query: ListingQuery) -> list[ListingRow]:
        statement = text(_LISTINGS_SQL.format(order=_ORDER_SQL[query.order])).bindparams(
            bindparam("search", type_=String),
            bindparam("pattern", type_=String),
            bindparam("in_stock", type_=Boolean),
            bindparam("changed_only", type_=Boolean),
            bindparam("limit", type_=Integer),
        )
        params: dict[str, Any] = {
            "search": query.search,
            "pattern": _like_pattern(query.search),
            "in_stock": query.in_stock,
            "changed_only": query.changed_only,
            "limit": query.limit,
        }
        async with self._engine.connect() as conn:
            rows = (await conn.execute(statement, params)).all()
        return [
            ListingRow(
                listing_id=ListingId(row.id),
                source_id=SourceId(row.source_id),
                external_id=row.external_id,
                title=row.title,
                url=row.url,
                pix=_price(row.pix_cents),
                card=_price(row.card_cents),
                in_stock=row.in_stock,
                collected_at=row.collected_at,
                points=row.points,
                next_collect_at=row.next_collect_at,
                change=row.chg,
                trend=tuple(row.trend or ()),
            )
            for row in rows
        ]

    async def history(
        self, listing_id: ListingId, since: datetime, limit: int = 2000
    ) -> ListingHistory | None:
        async with self._engine.connect() as conn:
            listing = (
                await conn.execute(
                    text("SELECT source_id, title, url FROM listings WHERE id = :id"),
                    {"id": listing_id},
                )
            ).first()
            if listing is None:
                return None
            rows = (
                await conn.execute(
                    text(_HISTORY_SQL),
                    {"listing_id": listing_id, "since": since, "limit": limit},
                )
            ).all()
        return ListingHistory(
            listing_id=listing_id,
            source_id=SourceId(listing.source_id),
            title=listing.title,
            url=listing.url,
            points=tuple(
                HistoryPoint(r.collected_at, _price(r.pix_cents), _price(r.card_cents), r.in_stock)
                for r in rows
            ),
        )

    async def activity(self, now: datetime, hours: int = 24) -> list[ActivityBucket]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(_ACTIVITY_SQL), {"now": now, "hours": hours})).all()
        return [ActivityBucket(hour=row.hour, points=row.points) for row in rows]
