"""initial schema: tenants, channels, catalog and price history

Revision ID: 0001
Revises:
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
    )
    op.create_table(
        "channels",
        sa.Column("id", UUID(as_uuid=True)),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id", name="pk_channels"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_channels_tenant_id_tenants"
        ),
        sa.UniqueConstraint("tenant_id", "kind", "target", name="uq_channels_tenant_id"),
    )
    op.create_table(
        "product_families",
        sa.Column("id", UUID(as_uuid=True)),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_product_families"),
        sa.UniqueConstraint("name", name="uq_product_families_name"),
    )
    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True)),
        sa.Column("family_id", UUID(as_uuid=True)),
        sa.Column("brand", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("mpn", sa.Text),
        sa.Column("ean", sa.Text),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.ForeignKeyConstraint(
            ["family_id"], ["product_families.id"], name="fk_products_family_id_product_families"
        ),
    )
    op.create_table(
        "listings",
        sa.Column("id", UUID(as_uuid=True)),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("product_id", UUID(as_uuid=True)),
        sa.Column("monitored", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_listings"),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_listings_product_id_products"
        ),
        sa.UniqueConstraint("source_id", "external_id", name="uq_listings_source_id"),
    )
    op.create_table(
        "price_points",
        sa.Column("listing_id", UUID(as_uuid=True), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pix_cents", sa.Integer),
        sa.Column("card_cents", sa.Integer),
        sa.Column("installments", sa.SmallInteger),
        sa.Column("in_stock", sa.Boolean, nullable=False),
        sa.PrimaryKeyConstraint("listing_id", "collected_at", name="pk_price_points"),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name="fk_price_points_listing_id_listings"
        ),
    )
    op.execute(
        "SELECT create_hypertable('price_points', by_range('collected_at', INTERVAL '7 days'))"
    )


def downgrade() -> None:
    op.drop_table("price_points")
    op.drop_table("listings")
    op.drop_table("products")
    op.drop_table("product_families")
    op.drop_table("channels")
    op.drop_table("tenants")
