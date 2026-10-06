"""Schema changes for databases created before a model change (the app has no migration tool).

Every step checks whether it is still needed, so running all of them on each startup is safe. They run before
`create_all`, which only creates missing tables and never alters existing ones."""
from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect, text

log = logging.getLogger("botyar.migrate")


def users_email_to_username(engine: Engine) -> bool:
    """2026-10-06: accounts sign in with a username instead of an email.

    Older databases have users.email. Copy it into the new users.username (so earlier accounts keep signing in with
    exactly what they typed before), make username unique, then drop email. One transaction on PostgreSQL."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return False  # a fresh database: create_all makes the new shape
    cols = {c["name"] for c in insp.get_columns("users")}
    if "email" not in cols:
        return False  # already migrated
    pg = engine.dialect.name == "postgresql"
    with engine.begin() as conn:
        if "username" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(255)"))
        conn.execute(text("UPDATE users SET username = LOWER(email) WHERE username IS NULL"))
        if not pg:  # SQLite cannot drop a column that still has an index; PostgreSQL drops dependent indexes itself
            for ix in inspect(conn).get_indexes("users"):
                if ix["column_names"] == ["email"]:
                    conn.execute(text(f'DROP INDEX "{ix["name"]}"'))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
        if pg:
            conn.execute(text("ALTER TABLE users ALTER COLUMN username SET NOT NULL"))
        conn.execute(text("ALTER TABLE users DROP COLUMN email"))
    log.warning("migrated users.email -> users.username")
    return True


def run_all(engine: Engine) -> None:
    users_email_to_username(engine)
