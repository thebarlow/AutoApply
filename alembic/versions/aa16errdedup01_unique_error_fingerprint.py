"""collapse duplicate error_events fingerprints and make fingerprint unique

Revision ID: aa16errdedup01
Revises: aa15errlog02
Create Date: 2026-11-16
"""

from alembic import op
import sqlalchemy as sa

revision = "aa16errdedup01"
down_revision = "aa15errlog02"
branch_labels = None
depends_on = None


def _collapse_duplicates(conn) -> None:
    """Merge rows sharing a fingerprint into the most recently seen one.

    The keeper (latest ``last_seen``, ties broken by highest ``id``) keeps its
    message/traceback/context — matching the handler's refresh-on-dedup
    semantics — and absorbs the summed ``count``, the earliest ``created_at``
    and the latest ``last_seen``. Done in Python so it runs identically on
    SQLite and Postgres.
    """
    dup_fps = [
        r[0]
        for r in conn.execute(
            sa.text(
                "SELECT fingerprint FROM error_events "
                "GROUP BY fingerprint HAVING COUNT(*) > 1"
            )
        )
    ]
    for fp in dup_fps:
        rows = conn.execute(
            sa.text(
                "SELECT id, created_at, last_seen, count FROM error_events "
                "WHERE fingerprint = :fp ORDER BY last_seen DESC, id DESC"
            ),
            {"fp": fp},
        ).all()
        keeper_id = rows[0].id
        total = sum(r.count or 1 for r in rows)
        first_seen = min(r.created_at for r in rows)
        last_seen = max(r.last_seen for r in rows)
        conn.execute(
            sa.text(
                "UPDATE error_events SET count = :c, created_at = :f, last_seen = :l "
                "WHERE id = :id"
            ),
            {"c": total, "f": first_seen, "l": last_seen, "id": keeper_id},
        )
        conn.execute(
            sa.text("DELETE FROM error_events WHERE fingerprint = :fp AND id <> :id"),
            {"fp": fp, "id": keeper_id},
        )


def upgrade() -> None:
    """Dedup existing rows, then swap the fingerprint index for a UNIQUE one."""
    _collapse_duplicates(op.get_bind())
    # CREATE/DROP INDEX is supported natively on both SQLite and Postgres, so no
    # batch_alter_table table-rebuild is needed.
    op.drop_index("ix_error_events_fingerprint", table_name="error_events")
    op.create_index(
        "ix_error_events_fingerprint", "error_events", ["fingerprint"], unique=True
    )


def downgrade() -> None:
    """Restore the non-unique fingerprint index (collapsed rows stay collapsed)."""
    op.drop_index("ix_error_events_fingerprint", table_name="error_events")
    op.create_index("ix_error_events_fingerprint", "error_events", ["fingerprint"])
