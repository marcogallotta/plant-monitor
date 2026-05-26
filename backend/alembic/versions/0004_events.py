"""Structured events: events, event_growing_units, event_photos

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note_text", sa.Text(), nullable=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("events_event_at_idx", "events", ["event_at"])
    op.create_index("events_event_type_idx", "events", ["event_type"])

    op.create_table(
        "event_growing_units",
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), primary_key=True),
        sa.Column("growing_unit_id", sa.Integer(), sa.ForeignKey("growing_units.id"), primary_key=True),
    )
    op.create_index("event_growing_units_unit_idx", "event_growing_units", ["growing_unit_id"])

    op.create_table(
        "event_photos",
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), primary_key=True),
        sa.Column("photo_id", sa.Integer(), sa.ForeignKey("photos.id"), primary_key=True),
    )
    op.create_index("event_photos_photo_idx", "event_photos", ["photo_id"])


def downgrade() -> None:
    op.drop_index("event_photos_photo_idx", "event_photos")
    op.drop_table("event_photos")
    op.drop_index("event_growing_units_unit_idx", "event_growing_units")
    op.drop_table("event_growing_units")
    op.drop_index("events_event_type_idx", "events")
    op.drop_index("events_event_at_idx", "events")
    op.drop_table("events")
