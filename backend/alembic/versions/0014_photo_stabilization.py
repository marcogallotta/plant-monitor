"""add per-photo stabilization transform (tilt/drift correction)

Pi overhead frames drift on a wind-nudged mount. An offline job
(scripts/compute_stabilization.py) registers each Pi frame onto a canonical
reference and stores the resulting 2x3 affine here so timelapse/compare can warp
frames to a common alignment client-side. NULL matrix = not stabilizable
(non-Pi source, or registration failed) -> the dashboard falls back to raw.

stab_matrix: the cv2 2x3 affine (target_frame_px -> reference_px) flattened
row-major [m00, m01, m02, m10, m11, m12]. stab_ref_w/h are the reference frame's
pixel dimensions the matrix was computed at, so the client can rescale the
translation terms to any display size.
"""
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade():
    op.add_column("photos", sa.Column("stab_matrix", JSONB(), nullable=True))
    op.add_column("photos", sa.Column("stab_ref_w", sa.Integer(), nullable=True))
    op.add_column("photos", sa.Column("stab_ref_h", sa.Integer(), nullable=True))
    op.add_column("photos", sa.Column("stab_status", sa.String(), nullable=True))


def downgrade():
    op.drop_column("photos", "stab_status")
    op.drop_column("photos", "stab_ref_h")
    op.drop_column("photos", "stab_ref_w")
    op.drop_column("photos", "stab_matrix")
