"""One-time port: copy a local SQLite DB into Postgres under a single tenant.

Stamps ``profile_id = tenant_id`` on tenant-owned tables, copies global tables
verbatim, and records ``Config dev_tenant_id = tenant_id``. Idempotency is NOT
guaranteed — run once against an empty destination schema.

Usage:
    python -m scripts.port_sqlite_to_pg \\
        --src sqlite:///auto_apply.db \\
        --dst postgresql+psycopg://auto_apply:auto_apply@localhost:5432/auto_apply
"""
from __future__ import annotations

import argparse

from sqlalchemy import MetaData, create_engine, insert, select, text

# Tables that gain profile_id; every other reflected table is copied verbatim.
TENANT_TABLES = {"jobs", "documents", "skill_aliases"}


def port(src_url: str, dst_url: str, tenant_id: int = 1) -> dict[str, int]:
    """Copy all rows from ``src_url`` into ``dst_url``; stamp tenant_id.

    Returns a per-table row-count dict for the post-port parity check.
    Assumes the destination schema already exists (Alembic head) and is empty.
    """
    src = create_engine(src_url)
    dst = create_engine(dst_url)

    src_meta = MetaData()
    src_meta.reflect(bind=src)
    dst_meta = MetaData()
    dst_meta.reflect(bind=dst)

    counts: dict[str, int] = {}
    with src.connect() as sconn, dst.begin() as dconn:
        for name, src_table in src_meta.tables.items():
            dst_table = dst_meta.tables.get(name)
            if dst_table is None:
                continue  # table not in destination schema; skip
            rows = [dict(r) for r in sconn.execute(select(src_table)).mappings().all()]
            if name in TENANT_TABLES:
                for r in rows:
                    if "profile_id" in dst_table.c:
                        r["profile_id"] = tenant_id
            # Keep only columns the destination actually has.
            cleaned = [{k: v for k, v in r.items() if k in dst_table.c} for r in rows]
            if cleaned:
                dconn.execute(insert(dst_table), cleaned)
            counts[name] = len(cleaned)

        existing = dconn.execute(
            text("SELECT value FROM config WHERE key='dev_tenant_id'")
        ).scalar()
        if existing is None:
            dconn.execute(
                text("INSERT INTO config (key, value) VALUES ('dev_tenant_id', :v)"),
                {"v": str(tenant_id)},
            )
        else:
            dconn.execute(
                text("UPDATE config SET value=:v WHERE key='dev_tenant_id'"),
                {"v": str(tenant_id)},
            )

    return counts


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", required=True, help="Source SQLite URL")
    p.add_argument("--dst", required=True, help="Destination Postgres URL")
    p.add_argument("--tenant-id", type=int, default=1)
    args = p.parse_args()
    counts = port(args.src, args.dst, args.tenant_id)
    print("[port] rows copied per table:")
    for name, n in sorted(counts.items()):
        print(f"  {name}: {n}")
    print(f"[port] dev_tenant_id set to {args.tenant_id}.")


if __name__ == "__main__":
    main()
