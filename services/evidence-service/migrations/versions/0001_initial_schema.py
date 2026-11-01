"""Gate 2/3 evidence, snapshot, confirmation, inbox, and outbox schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_evidence_gate23"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "care_episodes",
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "encounter_status", sa.String(32), nullable=False, server_default="OPEN"
        ),
        sa.Column(
            "presence_status",
            sa.String(32),
            nullable=False,
            server_default="QR_VERIFIED",
        ),
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_acked_source_sequence",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("expected_final_sequence", sa.Integer()),
        sa.Column(
            "sync_status", sa.String(32), nullable=False, server_default="RECEIVING"
        ),
        sa.Column("checked_out_at", sa.DateTime(timezone=True)),
        sa.Column("sync_completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "encounter_status IN ('OPEN','CHECKED_OUT','CLOSED_WITH_EXCEPTION','CANCELLED')"
        ),
        sa.CheckConstraint(
            "sync_status IN ('RECEIVING','SYNC_COMPLETE','INCOMPLETE_SYNC','QUARANTINE_PENDING')"
        ),
    )
    op.create_index(
        "ix_care_episodes_organization_id", "care_episodes", ["organization_id"]
    )
    op.create_index("ix_care_episodes_patient_id", "care_episodes", ["patient_id"])
    op.create_table(
        "evidence_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("care_episodes.encounter_id"),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system_id", sa.String(64), nullable=False),
        sa.Column("external_record_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "kind IN ('DIAGNOSIS','PROCEDURE','MEDICATION_PRESCRIBED','MEDICATION_DISPENSE','STAGE_COMPLETION','DOCUMENT_FINGERPRINT')"
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','CORRECTED','CANCELLED','QUARANTINED')"
        ),
        sa.UniqueConstraint(
            "organization_id", "source_system_id", "external_record_id"
        ),
    )
    op.create_index(
        "idx_evidence_records_enc", "evidence_records", ["encounter_id", "status"]
    )
    op.create_table(
        "evidence_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "evidence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_records.id"),
            nullable=False,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("care_episodes.encounter_id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_event_id", sa.String(128), nullable=False),
        sa.Column("source_sequence", sa.Integer(), nullable=False),
        sa.Column("event_action", sa.String(32), nullable=False),
        sa.Column("code_system", sa.String(64), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("canonical_code_system", sa.String(64)),
        sa.Column("canonical_code", sa.String(64)),
        sa.Column(
            "mapping_status", sa.String(32), nullable=False, server_default="MAPPED"
        ),
        sa.Column("display_text", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4)),
        sa.Column("unit", sa.String(32)),
        sa.Column("canonical_quantity", sa.Numeric(12, 4)),
        sa.Column("canonical_unit", sa.String(32)),
        sa.Column("stage_completion", sa.String(32)),
        sa.Column("source_actor_id", sa.String(128), nullable=False),
        sa.Column("source_actor_role", sa.String(64), nullable=False),
        sa.Column(
            "actor_assurance",
            sa.String(32),
            nullable=False,
            server_default="SOURCE_ASSERTED",
        ),
        sa.Column("change_reason", sa.Text()),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("event_action IN ('RECORDED','CORRECTED','CANCELLED')"),
        sa.CheckConstraint("mapping_status IN ('MAPPED','UNSUPPORTED_MAPPING')"),
        sa.UniqueConstraint("evidence_id", "version"),
        sa.UniqueConstraint("encounter_id", "source_event_id"),
        sa.UniqueConstraint("encounter_id", "source_sequence"),
    )
    op.create_index(
        "idx_evidence_versions_enc", "evidence_versions", ["encounter_id", "version"]
    )
    op.create_table(
        "evidence_quarantine",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_event_id", sa.String(128), nullable=False),
        sa.Column("external_record_id", sa.String(128), nullable=False),
        sa.Column("received_version", sa.Integer(), nullable=False),
        sa.Column("current_known_version", sa.Integer()),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "reason_code IN ('OUT_OF_ORDER_VERSION','UNKNOWN_ENCOUNTER','SCHEMA_MISMATCH')"
        ),
        sa.UniqueConstraint("organization_id", "source_system", "source_event_id"),
    )
    op.create_table(
        "care_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("care_episodes.encounter_id"),
            nullable=False,
        ),
        sa.Column("stage_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("status IN ('STARTED','STAFF_COMPLETED','CANCELLED')"),
    )
    op.create_index("idx_care_stages_enc", "care_stages", ["encounter_id"])
    op.create_table(
        "summary_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("care_episodes.encounter_id"),
            nullable=False,
        ),
        sa.Column("evidence_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("items_json", postgresql.JSONB(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("presented_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('READY','INCOMPLETE_SYNC','OUTDATED','RECONFIRMATION_REQUIRED')"
        ),
        sa.UniqueConstraint("encounter_id", "evidence_revision"),
    )
    op.create_index(
        "ix_summary_snapshots_encounter_id", "summary_snapshots", ["encounter_id"]
    )
    op.create_table(
        "patient_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("summary_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("care_episodes.encounter_id"),
            nullable=False,
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_type", sa.String(32), nullable=False),
        sa.Column(
            "method", sa.String(32), nullable=False, server_default="PATIENT_APP"
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column(
            "superseded_by_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("summary_snapshots.id"),
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "response_type IN ('CONFIRMED','PARTIALLY_DISPUTED','DISPUTED','DECLINED','NO_RESPONSE')"
        ),
    )
    op.create_index(
        "idx_patient_responses_enc",
        "patient_responses",
        ["encounter_id", "submitted_at"],
    )
    op.create_table(
        "patient_item_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "response_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_responses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_records.id"),
            nullable=False,
        ),
        sa.Column(
            "evidence_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_versions.id"),
            nullable=False,
        ),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64)),
        sa.Column("note_ciphertext", sa.LargeBinary()),
        sa.CheckConstraint("result IN ('CONFIRMED','DISPUTED')"),
        sa.UniqueConstraint("response_id", "evidence_id"),
    )
    for name in ("evidence_outbox",):
        op.create_table(
            name,
            sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("event_type", sa.String(128), nullable=False),
            sa.Column("aggregate_id", sa.String(128), nullable=False),
            sa.Column("aggregate_revision", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(128), nullable=False),
            sa.Column("correlation_id", sa.String(128), nullable=False),
            sa.Column("causation_id", sa.String(128)),
            sa.Column("payload", postgresql.JSONB(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
    op.create_index("ix_evidence_outbox_created_at", "evidence_outbox", ["created_at"])
    op.create_table(
        "evidence_inbox",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    for table in (
        "evidence_inbox",
        "evidence_outbox",
        "patient_item_responses",
        "patient_responses",
        "summary_snapshots",
        "care_stages",
        "evidence_quarantine",
        "evidence_versions",
        "evidence_records",
        "care_episodes",
    ):
        op.drop_table(table)
