"""add original_size_bytes to photos"""
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("photos", sa.Column("original_size_bytes", sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column("photos", "original_size_bytes")
