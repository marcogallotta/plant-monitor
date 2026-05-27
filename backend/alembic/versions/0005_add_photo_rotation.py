"""Add rotation to photos

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("rotation", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("photos", "rotation")
