"""Add missing visit columns to simrs_b_visits.

Revision ID: 0002_add_visit_columns
Revises: 0001_simrs_b_gate8
Create Date: 2026-10-30
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_visit_columns"
down_revision = "0001_simrs_b_gate8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("simrs_b_visits")}
    additions = (
        ("participant_number", sa.Column("participant_number", sa.String(length=64), nullable=True)),
        ("external_visit_reference", sa.Column("external_visit_reference", sa.String(length=128), nullable=True)),
        ("status", sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN")),
        ("presence_status", sa.Column("presence_status", sa.String(length=32), nullable=False, server_default="QR_VERIFIED")),
        ("checked_in_at", sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True)),
        ("checked_out_at", sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True)),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("simrs_b_visits", column)


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("simrs_b_visits")}
    for name in ("checked_out_at", "checked_in_at", "presence_status", "status", "external_visit_reference", "participant_number"):
        if name in columns:
            op.drop_column("simrs_b_visits", name)
