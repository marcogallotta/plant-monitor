"""add humidity_pct to sensor_readings for SwitchBot Meter ingest

Revision ID: 0018
Revises: 06582a2d1c12
"""
revision = "0018"
down_revision = "06582a2d1c12"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("sensor_readings", sa.Column("humidity_pct", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("sensor_readings", "humidity_pct")
