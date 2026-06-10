"""deduplicate sensor_readings by minute

Revision ID: 06582a2d1c12
Revises: 0016
Create Date: 2026-06-10 12:05:43.300821

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '06582a2d1c12'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Delete duplicate rows caused by wall_now drift: keep the lowest id per (mac, minute).
    op.execute("""
        DELETE FROM sensor_readings
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM sensor_readings
            GROUP BY mac, date_trunc('minute', recorded_at)
        )
    """)

    # Truncate all existing recorded_at values to minute precision so the
    # existing unique constraint on (mac, recorded_at) enforces dedup going forward.
    op.execute("""
        UPDATE sensor_readings
        SET recorded_at = date_trunc('minute', recorded_at)
    """)


def downgrade() -> None:
    pass
