"""Initial canonical catalog, discovery, operations, and voting schema.

Revision ID: 20260830_0001
Revises:
Create Date: 2026-08-30
"""

from alembic import op
from romanpics_api.models import Base

revision = "20260830_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Base.metadata is intentional for the baseline snapshot: the migration is
    # frozen with v0.1 and tested on SQLite and PostgreSQL-generated SQL. Future
    # revisions must use explicit Alembic operations.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
