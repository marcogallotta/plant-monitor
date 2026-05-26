"""Create photos and photo_notes tables

Revision ID: 0001
Revises:
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("metadata_path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filename", name="photos_filename_uniq"),
    )
    op.create_index("photos_captured_at_idx", "photos", ["captured_at"])

    op.create_table(
        "photo_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("photo_id", sa.Integer(), nullable=False),
        sa.Column("note_text", sa.Text(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("x >= 0.0 AND x <= 1.0", name="photo_notes_x_range"),
        sa.CheckConstraint("y >= 0.0 AND y <= 1.0", name="photo_notes_y_range"),
    )


def downgrade() -> None:
    op.drop_table("photo_notes")
    op.drop_index("photos_captured_at_idx", "photos")
    op.drop_table("photos")
