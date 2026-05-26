"""Stage 3 schema: locations, growing_units, photo_growing_units, photo identity fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "growing_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("unit_type", sa.String(), nullable=True),
        sa.Column("species", sa.String(), nullable=True),
        sa.Column("variety", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("current_location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.add_column("photos", sa.Column("source", sa.String(), nullable=True))
    op.add_column("photos", sa.Column("photo_type", sa.String(), nullable=True))
    op.add_column("photos", sa.Column("original_filename", sa.String(), nullable=True))
    op.add_column("photos", sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True))

    op.execute("UPDATE photos SET source = 'manual' WHERE source IS NULL")

    op.create_index("photos_source_idx", "photos", ["source"])
    op.create_index("photos_photo_type_idx", "photos", ["photo_type"])
    op.create_index("photos_location_id_idx", "photos", ["location_id"])

    op.create_table(
        "photo_growing_units",
        sa.Column("photo_id", sa.Integer(), sa.ForeignKey("photos.id"), primary_key=True),
        sa.Column("growing_unit_id", sa.Integer(), sa.ForeignKey("growing_units.id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("photo_growing_units_growing_unit_id_idx", "photo_growing_units", ["growing_unit_id"])
    op.create_index("growing_units_current_location_id_idx", "growing_units", ["current_location_id"])


def downgrade() -> None:
    op.drop_index("growing_units_current_location_id_idx", "growing_units")
    op.drop_index("photo_growing_units_growing_unit_id_idx", "photo_growing_units")
    op.drop_table("photo_growing_units")
    op.drop_index("photos_location_id_idx", "photos")
    op.drop_index("photos_photo_type_idx", "photos")
    op.drop_index("photos_source_idx", "photos")
    op.drop_column("photos", "location_id")
    op.drop_column("photos", "original_filename")
    op.drop_column("photos", "photo_type")
    op.drop_column("photos", "source")
    op.drop_table("growing_units")
    op.drop_table("locations")
