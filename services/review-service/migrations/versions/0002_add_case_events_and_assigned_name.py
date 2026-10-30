"""Add assigned_name to review_cases and create case_events table."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_review_case_events"
down_revision = "0001_review_gate6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("review_cases")}
    if "assigned_name" not in columns:
        op.add_column(
            "review_cases",
            sa.Column("assigned_name", sa.String(128), nullable=True),
        )
    if "case_events" not in inspector.get_table_names():
        op.create_table(
            "case_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "case_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("review_cases.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("actor_name", sa.String(128), nullable=False),
            sa.Column("code", sa.String(32), nullable=True),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "case_events" in inspector.get_table_names():
        op.drop_table("case_events")
    columns = {column["name"] for column in inspector.get_columns("review_cases")}
    if "assigned_name" in columns:
        op.drop_column("review_cases", "assigned_name")
