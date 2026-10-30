"""Add display column to verification_request_items."""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_display_column"
down_revision = "0001_verification_gate45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("verification_request_items")}
    if "display" not in columns:
        op.add_column(
            "verification_request_items",
            sa.Column("display", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("verification_request_items")}
    if "display" in columns:
        op.drop_column("verification_request_items", "display")
