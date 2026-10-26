"""Gate 8 SIMRS-B local records and durable outbox."""

from alembic import op

from app.domain.models import Base

revision = "0001_simrs_b_gate8"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
