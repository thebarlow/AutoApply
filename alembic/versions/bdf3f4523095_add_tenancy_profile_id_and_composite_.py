"""add tenancy profile_id and composite constraints

Revision ID: bdf3f4523095
Revises: 3433821457fb
Create Date: 2026-06-10 16:26:45.002143

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bdf3f4523095'
down_revision: Union[str, Sequence[str], None] = '3433821457fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTE: profile_id is added NOT NULL here because the Phase-1 baseline
    # targets an empty Postgres DB. Phase 3's data port (which migrates
    # existing SQLite rows into a real Postgres install) MUST stamp
    # profile_id=1 on all existing jobs/documents/skill_aliases rows BEFORE
    # this migration runs, or add the column nullable first, backfill, then
    # ALTER to NOT NULL.
    #
    # Wrapped in batch_alter_table so this also works on SQLite (used by the
    # alembic-vs-create_all parity test), which can't ALTER constraints
    # in-place and instead does a copy-and-move.
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('profile_id', sa.Integer(), nullable=False))
        batch_op.drop_constraint('uq_documents_job_type', type_='unique')
        batch_op.create_index(batch_op.f('ix_documents_profile_id'), ['profile_id'], unique=False)
        batch_op.create_unique_constraint('uq_documents_profile_job_type', ['profile_id', 'job_key', 'doc_type'])

    # The old single-column unique constraints on jobs.job_key/jobs.url have
    # auto-generated names on Postgres (jobs_job_key_key / jobs_url_key) but
    # are unnamed on SQLite. Drop by the dialect-appropriate strategy: named
    # drop on Postgres; on SQLite, recreate the table from a reflected copy
    # with those unnamed unique constraints stripped.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.batch_alter_table('jobs', schema=None) as batch_op:
            batch_op.add_column(sa.Column('profile_id', sa.Integer(), nullable=False))
            batch_op.drop_constraint('jobs_job_key_key', type_='unique')
            batch_op.drop_constraint('jobs_url_key', type_='unique')
            batch_op.create_index(batch_op.f('ix_jobs_profile_id'), ['profile_id'], unique=False)
            batch_op.create_unique_constraint('uq_jobs_profile_job_key', ['profile_id', 'job_key'])
            batch_op.create_unique_constraint('uq_jobs_profile_url', ['profile_id', 'url'])
    else:
        reflected = sa.Table('jobs', sa.MetaData(), autoload_with=bind)
        reflected.constraints = {
            c for c in reflected.constraints
            if not (isinstance(c, sa.UniqueConstraint) and c.name is None)
        }
        with op.batch_alter_table('jobs', schema=None, copy_from=reflected, recreate='always') as batch_op:
            batch_op.add_column(sa.Column('profile_id', sa.Integer(), nullable=False))
            batch_op.create_index(batch_op.f('ix_jobs_profile_id'), ['profile_id'], unique=False)
            batch_op.create_unique_constraint('uq_jobs_profile_job_key', ['profile_id', 'job_key'])
            batch_op.create_unique_constraint('uq_jobs_profile_url', ['profile_id', 'url'])

    # skill_aliases moves from a single-column PK (alias_key) to a composite
    # PK (profile_id, alias_key). Autogenerate doesn't detect PK changes, so
    # this is hand-written: drop the old PK, then create the composite one.
    # The old PK is named 'skill_aliases_pkey' on Postgres but unnamed on
    # SQLite; on SQLite, recreate the table from a reflected copy with the
    # old (unnamed) PK constraint stripped.
    if bind.dialect.name == "postgresql":
        with op.batch_alter_table('skill_aliases', schema=None) as batch_op:
            batch_op.add_column(sa.Column('profile_id', sa.Integer(), nullable=False))
            batch_op.drop_constraint('skill_aliases_pkey', type_='primary')
            batch_op.create_primary_key('skill_aliases_pkey', ['profile_id', 'alias_key'])
    else:
        reflected = sa.Table('skill_aliases', sa.MetaData(), autoload_with=bind)
        reflected.constraints = {
            c for c in reflected.constraints if not isinstance(c, sa.PrimaryKeyConstraint)
        }
        reflected.columns['alias_key'].primary_key = False
        with op.batch_alter_table('skill_aliases', schema=None, copy_from=reflected, recreate='always') as batch_op:
            batch_op.add_column(sa.Column('profile_id', sa.Integer(), nullable=False))
            batch_op.create_primary_key('skill_aliases_pkey', ['profile_id', 'alias_key'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('skill_aliases', schema=None) as batch_op:
        batch_op.drop_constraint('skill_aliases_pkey', type_='primary')
        batch_op.create_primary_key('skill_aliases_pkey', ['alias_key'])
        batch_op.drop_column('profile_id')

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_jobs_profile_url', type_='unique')
        batch_op.drop_constraint('uq_jobs_profile_job_key', type_='unique')
        batch_op.drop_index(batch_op.f('ix_jobs_profile_id'))
        batch_op.create_unique_constraint('jobs_url_key', ['url'])
        batch_op.create_unique_constraint('jobs_job_key_key', ['job_key'])
        batch_op.drop_column('profile_id')

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_constraint('uq_documents_profile_job_type', type_='unique')
        batch_op.drop_index(batch_op.f('ix_documents_profile_id'))
        batch_op.create_unique_constraint('uq_documents_job_type', ['job_key', 'doc_type'])
        batch_op.drop_column('profile_id')
