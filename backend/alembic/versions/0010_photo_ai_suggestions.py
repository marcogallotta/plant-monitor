"""add photo_ai_suggestions table"""
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade():
    op.create_table(
        "photo_ai_suggestions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("photo_id", sa.Integer, sa.ForeignKey("photos.id"), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("batch_hint", sa.Text, nullable=True),
        sa.Column("prompt_context", JSONB, nullable=True),
        sa.Column("x", sa.Float, nullable=True),
        sa.Column("y", sa.Float, nullable=True),
        sa.Column("x2", sa.Float, nullable=True),
        sa.Column("y2", sa.Float, nullable=True),
        sa.Column("suggested_plant_id", sa.Integer, sa.ForeignKey("growing_units.id"), nullable=True),
        sa.Column("suggested_plant_name", sa.Text, nullable=True),
        sa.Column("suggested_photo_type", sa.Text, nullable=True),
        sa.Column("suggested_rotation", sa.Integer, nullable=True),
        sa.Column("suggested_labels", JSONB, nullable=True),
        sa.Column("confidence", sa.Text, nullable=True),
        sa.Column("question", sa.Text, nullable=True),
        sa.Column("observation", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'edited', 'rejected', 'deleted')", name="photo_ai_suggestions_status_check"),
        sa.CheckConstraint("confidence IN ('high', 'medium', 'low')", name="photo_ai_suggestions_confidence_check"),
        sa.CheckConstraint("suggested_rotation IS NULL OR suggested_rotation IN (0, 90, 180, 270)", name="photo_ai_suggestions_rotation_check"),
        sa.Column("edited_plant_id", sa.Integer, sa.ForeignKey("growing_units.id"), nullable=True),
        sa.Column("edited_photo_type", sa.Text, nullable=True),
        sa.Column("edited_labels", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("photo_ai_suggestions_photo_id_idx", "photo_ai_suggestions", ["photo_id"])
    op.create_index("photo_ai_suggestions_status_idx", "photo_ai_suggestions", ["status"])


def downgrade():
    op.drop_index("photo_ai_suggestions_status_idx", table_name="photo_ai_suggestions")
    op.drop_index("photo_ai_suggestions_photo_id_idx", table_name="photo_ai_suggestions")
    op.drop_table("photo_ai_suggestions")
