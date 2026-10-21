"""Table definitions. Collection data (catalog, prices) is global and shared by all
tenants; anything a channel owner configures carries tenant_id."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Interval,
    MetaData,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

tenants = Table(
    "tenants",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

channels = Table(
    "channels",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("target", Text, nullable=False),
    Column("enabled", Boolean, nullable=False, server_default="true"),
    UniqueConstraint("tenant_id", "kind", "target"),
)

product_families = Table(
    "product_families",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column("category", Text, nullable=False),
)

products = Table(
    "products",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("family_id", UUID(as_uuid=True), ForeignKey("product_families.id")),
    Column("brand", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("mpn", Text),
    Column("ean", Text),
)

listings = Table(
    "listings",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("source_id", Text, nullable=False),
    Column("external_id", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("product_id", UUID(as_uuid=True), ForeignKey("products.id")),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    # Collection schedule: both set for monitored listings, both null otherwise.
    Column("collect_interval", Interval),
    Column("next_collect_at", DateTime(timezone=True)),
    UniqueConstraint("source_id", "external_id"),
    CheckConstraint(
        "(collect_interval IS NULL) = (next_collect_at IS NULL)", name="schedule_complete"
    ),
    Index(
        "ix_listings_next_collect_at",
        "next_collect_at",
        postgresql_where="next_collect_at IS NOT NULL",
    ),
)

# TimescaleDB hypertable partitioned by collected_at (see the initial migration).
price_points = Table(
    "price_points",
    metadata,
    Column("listing_id", UUID(as_uuid=True), ForeignKey("listings.id"), primary_key=True),
    Column("collected_at", DateTime(timezone=True), primary_key=True),
    Column("pix_cents", Integer),
    Column("card_cents", Integer),
    Column("installments", SmallInteger),
    Column("in_stock", Boolean, nullable=False),
)
