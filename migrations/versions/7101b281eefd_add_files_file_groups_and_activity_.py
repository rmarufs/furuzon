"""add files file_groups and activity tables

Revision ID: 7101b281eefd
Revises: 25902e563ba9
Create Date: 2026-11-04 16:42:29.695239
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7101b281eefd"
down_revision: str | Sequence[str] | None = "25902e563ba9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=True),
        sa.Column("object_title", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_activity_owner_id_created_at",
        "activity",
        ["owner_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("course", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("public_token", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("course >= 1 AND course <= 6", name="ck_files_course"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_token"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_files_owner_id", "files", ["owner_id"], unique=False)
    op.create_table(
        "file_groups",
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("file_id", "group_id"),
    )
    op.create_index(
        "ix_file_groups_group_id",
        "file_groups",
        ["group_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_file_groups_group_id", table_name="file_groups")
    op.drop_table("file_groups")
    op.drop_index("ix_files_owner_id", table_name="files")
    op.drop_table("files")
    op.drop_index("ix_activity_owner_id_created_at", table_name="activity")
    op.drop_table("activity")
