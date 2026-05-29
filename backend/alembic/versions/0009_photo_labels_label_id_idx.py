"""add index on photo_labels.label_id"""
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    op.create_index("photo_labels_label_id_idx", "photo_labels", ["label_id"])


def downgrade():
    op.drop_index("photo_labels_label_id_idx", table_name="photo_labels")
