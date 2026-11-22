"""Database helpers for pipeline tests."""

from pathlib import Path

from ingest.sqlite import connect
from pipeline.run import SIMULATION_TABLES


def write_table(
    db_path: Path,
    table: str,
    columns: list[str],
    rows: list[tuple[object, ...]],
) -> None:
    """Create a table and insert rows."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    with connect(db_path) as conn:
        conn.execute(f'CREATE TABLE "{table}" ({quoted_columns})')
        if rows:
            conn.executemany(
                f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})',
                rows,
            )


def apply_simulation_schema(db_path: Path) -> None:
    """Create the simulation tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SIMULATION_TABLES.read_text())


def query(
    db_path: Path,
    sql: str,
    params: tuple[object, ...] = (),
) -> list[tuple[object, ...]]:
    """Return every row from sql."""
    with connect(db_path) as conn:
        return list(conn.execute(sql, params).fetchall())
