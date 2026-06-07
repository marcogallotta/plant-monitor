"""add content_hash to photos for byte-identical dedup"""
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("photos", sa.Column("content_hash", sa.String(), nullable=True))
    # NULLs are distinct in Postgres, so existing rows (and Pi uploads, which
    # don't set a hash) coexist; only populated hashes are forced unique.
    op.create_index("photos_content_hash_unique_idx", "photos", ["content_hash"], unique=True)


def downgrade():
    op.drop_index("photos_content_hash_unique_idx", table_name="photos")
    op.drop_column("photos", "content_hash")
