"""Add x2/y2 rect columns to photo_notes

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("photo_notes", sa.Column("x2", sa.Float(), nullable=True))
    op.add_column("photo_notes", sa.Column("y2", sa.Float(), nullable=True))
    op.create_check_constraint(
        "photo_notes_x2_range", "photo_notes",
        "x2 IS NULL OR (x2 >= 0.0 AND x2 <= 1.0)",
    )
    op.create_check_constraint(
        "photo_notes_y2_range", "photo_notes",
        "y2 IS NULL OR (y2 >= 0.0 AND y2 <= 1.0)",
    )


def downgrade() -> None:
    op.drop_constraint("photo_notes_y2_range", "photo_notes", type_="check")
    op.drop_constraint("photo_notes_x2_range", "photo_notes", type_="check")
    op.drop_column("photo_notes", "y2")
    op.drop_column("photo_notes", "x2")
