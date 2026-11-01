"""Gate 6 review and audit schema."""

from alembic import op

from app.infrastructure.models import Base

revision = "0001_review_gate6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
