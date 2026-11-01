"""Visit header fields the facility worklist needs."""

from alembic import op
import sqlalchemy as sa

revision = "0002_simrs_a_worklist"
down_revision = "0001_simrs_a_gate2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("simrs_visits", sa.Column("participant_number", sa.String(64)))
    op.add_column("simrs_visits", sa.Column("external_visit_reference", sa.String(128)))
    op.add_column(
        "simrs_visits",
        sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),
    )
    op.add_column(
        "simrs_visits",
        sa.Column(
            "presence_status",
            sa.String(32),
            nullable=False,
            server_default="QR_VERIFIED",
        ),
    )
    op.add_column("simrs_visits", sa.Column("checked_in_at", sa.DateTime(timezone=True)))
    op.add_column("simrs_visits", sa.Column("checked_out_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    for column in (
        "checked_out_at",
        "checked_in_at",
        "presence_status",
        "status",
        "external_visit_reference",
        "participant_number",
    ):
        op.drop_column("simrs_visits", column)
