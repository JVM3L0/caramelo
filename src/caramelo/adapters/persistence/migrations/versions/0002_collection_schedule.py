"""collection schedule per listing (monitored catalog)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("listings", "monitored")
    op.add_column("listings", sa.Column("collect_interval", sa.Interval))
    op.add_column("listings", sa.Column("next_collect_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_listings_schedule_complete",
        "listings",
        "(collect_interval IS NULL) = (next_collect_at IS NULL)",
    )
    op.create_index(
        "ix_listings_next_collect_at",
        "listings",
        ["next_collect_at"],
        postgresql_where=sa.text("next_collect_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_listings_next_collect_at", table_name="listings")
    op.drop_constraint("ck_listings_schedule_complete", "listings", type_="check")
    op.drop_column("listings", "next_collect_at")
    op.drop_column("listings", "collect_interval")
    op.add_column(
        "listings",
        sa.Column("monitored", sa.Boolean, nullable=False, server_default="true"),
    )
