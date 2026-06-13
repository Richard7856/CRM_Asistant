"""
One-shot dev fix (P0.8): ensure every Postgres enum type has a label for each
member NAME of its Python enum.

WHY: SQLAlchemy binds enum member NAMES (uppercase) at runtime, but the early
migrations created some enum types from the lowercase dotted VALUES (verified:
dev `auditeventtype` holds 'auth.login.success' while the ORM binds
'LOGIN_SUCCESS'). That mismatch makes ORM writes of those enums fail against dev.
This adds any MISSING name-labels (existing labels stay — non-destructive) so dev
matches what create_all produces for the test DB. Idempotent.

The real cleanup (recreate the types cleanly) waits until there's a prod DB to
migrate; new migrations already use NAMES (see P0.7). This just makes dev usable.

Run from backend/ with the venv active:
    python -m scripts.sync_dev_enum_labels
"""

import asyncio

from sqlalchemy import Enum as SAEnum
from sqlalchemy import text

import app.main  # noqa: F401 — imports all routers → registers every model on Base
from app.core.database import Base, engine


async def main() -> None:
    added = 0
    # AUTOCOMMIT: ALTER TYPE ... ADD VALUE is happiest outside a transaction block.
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        seen: set[tuple[str, str]] = set()
        for table in Base.metadata.tables.values():
            for col in table.columns:
                col_type = col.type
                if not isinstance(col_type, SAEnum) or col_type.enum_class is None:
                    continue
                type_name = col_type.name
                for member in col_type.enum_class:
                    key = (type_name, member.name)
                    if key in seen:
                        continue
                    seen.add(key)
                    # type_name + member.name come from our own code, never user input.
                    await conn.execute(
                        text(
                            f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{member.name}'"
                        )
                    )
                    added += 1
    print(f"Enum label sync complete — checked/added {added} member labels.")


if __name__ == "__main__":
    asyncio.run(main())
