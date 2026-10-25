"""Gate 1 encounter, QR receipt, exception, and outbox schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_encounter_gate1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code_namespace", sa.String(64), nullable=False),
        sa.Column("external_code", sa.String(64), nullable=False),
        sa.Column("org_type", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("org_type IN ('FASKES','VERIFIER_ORG','SYSTEM')"),
        sa.CheckConstraint("status IN ('ACTIVE','DISABLED')"),
        sa.UniqueConstraint("code_namespace", "external_code"),
    )
    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("participant_lookup_key", sa.String(64), nullable=False, unique=True),
        sa.Column("participant_number_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("display_name_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("display_name_normalized_hmac", sa.String(64), nullable=False),
        sa.Column("identity_assurance", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("identity_assurance IN ('VERIFIED_PARTICIPANT_ID','VERIFIED_EXTERNAL_ID','LOW_IDENTITY_ASSURANCE')"),
    )
    op.create_index("ix_patients_participant_lookup_key", "patients", ["participant_lookup_key"], unique=True)
    op.create_index("ix_patients_display_name_normalized_hmac", "patients", ["display_name_normalized_hmac"])
    op.create_table(
        "patient_external_ids",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("source_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("identity_type", sa.String(64), nullable=False),
        sa.Column("assurance", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_system_id", "identity_type", "external_id"),
    )
    op.create_table(
        "source_systems",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("client_id", sa.String(128), nullable=False, unique=True),
        sa.Column("source_code", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("mapping_version", sa.String(32), nullable=False, server_default="map-v1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('SIMRS_ADAPTER','SCANNER_TERMINAL','VERIFIER_PORTAL')"),
    )
    op.create_table(
        "encounters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("source_system_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_systems.id")),
        sa.Column("external_visit_reference", sa.String(128)),
        sa.Column("service_type", sa.String(32), nullable=False, server_default="OUTPATIENT"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("presence_status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("service_type IN ('OUTPATIENT','INPATIENT','EMERGENCY')"),
        sa.CheckConstraint("status IN ('OPEN','CHECKED_OUT','CLOSED_WITH_EXCEPTION','CANCELLED')"),
        sa.CheckConstraint("presence_status IN ('QR_VERIFIED','EXCEPTION_DOCUMENTED','UNVERIFIED')"),
    )
    op.create_index("idx_encounters_org_patient_started", "encounters", ["organization_id", "patient_id", "started_at", "ended_at"])
    op.create_index("idx_encounters_org_started", "encounters", ["organization_id", "started_at"])
    op.create_table(
        "qr_redemption_receipts",
        sa.Column("nonce_digest", sa.String(64), primary_key=True),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("scanner_client_id", sa.String(128), nullable=False),
        sa.Column("scanner_external_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("result", sa.String(32), nullable=False, server_default="COMMITTED"),
        sa.Column("response_payload", postgresql.JSONB(), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("purpose IN ('CHECK_IN','CHECK_OUT')"),
        sa.UniqueConstraint("scanner_client_id", "idempotency_key"),
    )
    op.create_table(
        "encounter_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("exception_phase", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=False),
        sa.Column("actor_assurance", sa.String(32), nullable=False, server_default="SOURCE_ASSERTED"),
        sa.Column("evidence_ref", sa.String(256)),
        sa.Column("notes", sa.Text()),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_encounter_exceptions_encounter_id", "encounter_exceptions", ["encounter_id"])
    op.create_table(
        "outbox_events",
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_outbox_events_created_at", "outbox_events", ["created_at"])
    op.create_table(
        "inbox_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in ("inbox_events", "outbox_events", "encounter_exceptions", "qr_redemption_receipts", "encounters", "source_systems", "patient_external_ids", "patients", "organizations"):
        op.drop_table(table)
