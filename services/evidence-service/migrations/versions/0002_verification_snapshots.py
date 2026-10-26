"""Add immutable evidence snapshots consumed by verification runs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_verification_snapshots"
down_revision = "0001_evidence_gate23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verification_evidence_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("care_episodes.encounter_id"), nullable=False),
        sa.Column("evidence_revision", sa.Integer(), nullable=False),
        sa.Column("episode_sync_status", sa.String(32), nullable=False),
        sa.Column("presence_status", sa.String(32), nullable=False),
        sa.Column("patient_confirmation_status", sa.String(32), nullable=False),
        sa.Column("pinned_items_json", postgresql.JSONB(), nullable=False),
        sa.Column("pinned_attestation_json", postgresql.JSONB()),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("encounter_id", "evidence_revision", "content_digest"),
    )
    op.create_index("ix_verification_evidence_snapshots_encounter_id", "verification_evidence_snapshots", ["encounter_id"])


def downgrade() -> None:
    op.drop_table("verification_evidence_snapshots")
