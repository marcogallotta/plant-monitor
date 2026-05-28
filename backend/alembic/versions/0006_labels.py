"""labels and photo_labels"""
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

COMMON_LABELS = [
    "watered",
    "fed_liquid",
    "fed_worm_castings",
    "harvested",
    "potted_up",
    "other",
]


def upgrade():
    op.create_table(
        "labels",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "photo_labels",
        sa.Column("photo_id", sa.Integer, sa.ForeignKey("photos.id"), primary_key=True),
        sa.Column("label_id", sa.Integer, sa.ForeignKey("labels.id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.bulk_insert(
        sa.table("labels", sa.column("name", sa.String)),
        [{"name": n} for n in COMMON_LABELS],
    )


def downgrade():
    op.drop_table("photo_labels")
    op.drop_table("labels")
