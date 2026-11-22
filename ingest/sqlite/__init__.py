import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Open the database at db_path with foreign keys on.

    Creates the file when it is missing. Commits on success and closes
    when the caller leaves the with-block.
    """
    path = Path(db_path).expanduser().resolve()
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect_sqlalchemy(db_path: str | Path) -> Iterator[Connection]:
    """Open a SQLAlchemy connection to the sqlite file with foreign keys enabled"""
    path = Path(db_path).expanduser().resolve()
    engine = create_engine(f"sqlite:///{path}")
    event.listen(
        engine,
        "connect",
        lambda dbapi_connection, _record: dbapi_connection.execute(
            "PRAGMA foreign_keys = ON"
        ),
    )
    conn = engine.connect()
    try:
        yield conn
    finally:
        conn.close()
        engine.dispose()


def table_exists(db_path: Path, table: str) -> bool:
    """Return whether table is already in the database file."""
    if not db_path.is_file():
        return False
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
    return row is not None


def apply_schema(db_path: Path) -> None:
    """Create any missing tables and views."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text())


def write_rows_to_table(
    db_path: Path,
    table: str,
    columns: tuple[str, ...],
    rows: list[tuple[object, ...]],
    *,
    replace: bool,
) -> None:
    placeholders = ", ".join("?" * len(columns))
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    with connect(db_path) as conn:
        if replace:
            conn.execute(f"DELETE FROM {table}")
        conn.executemany(sql, rows)
