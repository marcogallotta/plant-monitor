"""add sensor_readings table for Xiaomi Flower Care data ingested from the Pi"""
revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mac", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("lux", sa.Integer(), nullable=True),
        sa.Column("moisture_pct", sa.Integer(), nullable=True),
        sa.Column("conductivity_us_cm", sa.Integer(), nullable=True),
    )
    op.create_index(
        "sensor_readings_mac_recorded_at_uniq",
        "sensor_readings",
        ["mac", "recorded_at"],
        unique=True,
    )
    op.create_index(
        "sensor_readings_recorded_at_idx",
        "sensor_readings",
        ["recorded_at"],
    )


def downgrade():
    op.drop_index("sensor_readings_recorded_at_idx", table_name="sensor_readings")
    op.drop_index("sensor_readings_mac_recorded_at_uniq", table_name="sensor_readings")
    op.drop_table("sensor_readings")
