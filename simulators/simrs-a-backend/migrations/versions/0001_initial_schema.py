"""Gate 2 SIMRS-A source records and durable adapter outbox."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_simrs_a_gate2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "simrs_visits",
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("next_source_sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sync_status", sa.String(32), nullable=False, server_default="LOCAL_ONLY"),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "clinical_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("simrs_visits.encounter_id"), nullable=False),
        sa.Column("external_record_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("encounter_id", "external_record_id"),
    )
    op.create_table(
        "clinical_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinical_records.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_event_id", sa.String(128), nullable=False, unique=True),
        sa.Column("source_sequence", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("record_id", "version"),
    )
    op.create_table(
        "sync_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("simrs_visits.encounter_id"), nullable=False),
        sa.Column("target_path", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("delivery_status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_sync_outbox_created_at", "sync_outbox", ["created_at"])


def downgrade() -> None:
    for table in ("sync_outbox", "clinical_versions", "clinical_records", "simrs_visits"):
        op.drop_table(table)
