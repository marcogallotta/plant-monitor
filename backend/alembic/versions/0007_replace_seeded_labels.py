"""replace care-action seed labels with observation labels"""
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

OLD_LABELS = [
    "watered",
    "fed_liquid",
    "fed_worm_castings",
    "harvested",
    "potted_up",
    "other",
]

NEW_LABELS = [
    "aphids",
    "yellowing",
    "mildew",
    "damage",
    "new_growth",
    "recovery",
    "watch",
]


def upgrade():
    conn = op.get_bind()
    labels = sa.table("labels", sa.column("id", sa.Integer), sa.column("name", sa.String))
    photo_labels = sa.table("photo_labels", sa.column("label_id", sa.Integer))

    old_ids = conn.execute(
        sa.select(labels.c.id).where(labels.c.name.in_(OLD_LABELS))
    ).scalars().all()

    if old_ids:
        conn.execute(photo_labels.delete().where(photo_labels.c.label_id.in_(old_ids)))
        conn.execute(labels.delete().where(labels.c.id.in_(old_ids)))

    op.bulk_insert(
        sa.table("labels", sa.column("name", sa.String)),
        [{"name": n} for n in NEW_LABELS],
    )


def downgrade():
    conn = op.get_bind()
    labels = sa.table("labels", sa.column("id", sa.Integer), sa.column("name", sa.String))
    photo_labels = sa.table("photo_labels", sa.column("label_id", sa.Integer))

    new_ids = conn.execute(
        sa.select(labels.c.id).where(labels.c.name.in_(NEW_LABELS))
    ).scalars().all()

    if new_ids:
        conn.execute(photo_labels.delete().where(photo_labels.c.label_id.in_(new_ids)))
        conn.execute(labels.delete().where(labels.c.id.in_(new_ids)))

    op.bulk_insert(
        sa.table("labels", sa.column("name", sa.String)),
        [{"name": n} for n in OLD_LABELS],
    )
