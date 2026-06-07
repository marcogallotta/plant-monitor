"""add growing_unit_id to photo_notes; allow null note_text

Region tagging: a note can tag a growing unit on a specific frame, and may be a
pure unit-tag (no prose), so note_text becomes nullable.
"""
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        "photo_notes",
        sa.Column("growing_unit_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "photo_notes_growing_unit_id_fkey",
        "photo_notes", "growing_units",
        ["growing_unit_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "photo_notes_growing_unit_id_idx", "photo_notes", ["growing_unit_id"]
    )
    op.alter_column("photo_notes", "note_text", existing_type=sa.Text(), nullable=True)


def downgrade():
    # Unit-only notes have NULL note_text; restoring the NOT NULL constraint would
    # fail on those rows. Backfill empty strings first (lossy but reversible-safe).
    op.execute("UPDATE photo_notes SET note_text = '' WHERE note_text IS NULL")
    op.alter_column("photo_notes", "note_text", existing_type=sa.Text(), nullable=False)
    op.drop_index("photo_notes_growing_unit_id_idx", table_name="photo_notes")
    op.drop_constraint("photo_notes_growing_unit_id_fkey", "photo_notes", type_="foreignkey")
    op.drop_column("photo_notes", "growing_unit_id")
