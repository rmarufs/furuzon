"""add first_name and last_name to users

Revision ID: 25902e563ba9
Revises: 419736f9b747
Create Date: 2026-10-31 22:50:52.086487
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "25902e563ba9"
down_revision: str | Sequence[str] | None = "419736f9b747"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "first_name",
            sa.String(length=50),
            server_default="",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "last_name",
            sa.String(length=50),
            server_default="",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
