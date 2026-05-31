"""add suggested_options to photo_ai_suggestions"""
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade():
    op.add_column("photo_ai_suggestions", sa.Column("suggested_options", JSONB, nullable=True))


def downgrade():
    op.drop_column("photo_ai_suggestions", "suggested_options")
