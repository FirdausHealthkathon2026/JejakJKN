"""Gate 4/5 verification schema."""

import hashlib
import json

from alembic import op

from app.infrastructure.models import Base, RuleCatalogVersion

revision = "0001_verification_gate45"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())
    configuration = {
        "rules": [f"R{number:03d}" for number in range(1, 15)],
        "policy": "deterministic-screening-not-fraud-decision",
    }
    digest = hashlib.sha256(
        json.dumps(configuration, sort_keys=True).encode()
    ).hexdigest()
    op.bulk_insert(
        RuleCatalogVersion.__table__,
        [
            {
                "version": "rules-1.0.0",
                "mapping_version": "map-v1.0",
                "configuration_json": configuration,
                "configuration_digest": digest,
            }
        ],
    )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
