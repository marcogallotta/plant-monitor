"""add stab_version to photos (stabilization algorithm/param fingerprint)

The incremental stabilizer reuses settled frames. To stop old transforms from
silently surviving a change to the algorithm, thresholds, or reference frame,
each computed row records the fingerprint it was produced with; the worker
recomputes any row whose fingerprint differs from the current one.
"""
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("photos", sa.Column("stab_version", sa.String(), nullable=True))


def downgrade():
    op.drop_column("photos", "stab_version")
