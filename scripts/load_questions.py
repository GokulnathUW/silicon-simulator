"""Load the pipeline scenarios into their own SQLite file.

python scripts/load_questions.py
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import setting_path
from questions.ad import ADS, REACTIONS
from questions.choice import CHOICE_QUESTIONS
from questions.yes_no import YES_NO_QUESTIONS

SCHEMA_PATH = ROOT / "sql" / "demo_questions.sql"


def question_rows() -> list[tuple[str, str, str | None, str | None]]:
    """Return one row per yes/no question, choice question, and ad."""
    rows: list[tuple[str, str, str | None, str | None]] = []
    for item in YES_NO_QUESTIONS:
        rows.append(
            (
                item.category,
                item.campaign,
                json.dumps(item.instructions),
                json.dumps(item.criteria),
            )
        )
    for item in CHOICE_QUESTIONS:
        rows.append(
            (
                item.category,
                item.campaign,
                json.dumps(item.instructions),
                json.dumps(item.choices),
            )
        )
    for campaign in ADS:
        rows.append(("score", campaign, None, None))
    return rows


def reaction_rows() -> list[tuple[str, str, str]]:
    """Return one row per reaction score."""
    return [
        (
            reaction.name,
            json.dumps(reaction.instructions),
            json.dumps(reaction.criteria),
        )
        for reaction in REACTIONS
    ]


def load_questions(db_path: Path) -> None:
    """Create db_path and replace its question and reaction rows."""
    if db_path.name == "persona.db":
        raise SystemExit("Refusing to write into persona.db. Use data/questions.db.")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    questions = question_rows()
    reactions = reaction_rows()

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        # 1. Create the tables.
        conn.executescript(SCHEMA_PATH.read_text())

        # 2. Write the questions.
        conn.executemany(
            """
            INSERT INTO questions
                (category, campaign, instructions_json, criteria_json)
            VALUES (?, ?, ?, ?)
            """,
            questions,
        )

        # 3. Write the reactions.
        conn.executemany(
            """
            INSERT INTO reactions (name, instructions_json, criteria_json)
            VALUES (?, ?, ?)
            """,
            reactions,
        )

    print(
        f"Wrote {len(questions)} questions and {len(reactions)} reactions to {db_path}"
    )


def main() -> None:
    """Load the scenarios into the questions database, or into a path you pass."""
    questions_db = setting_path("QUESTIONS_DB")
    parser = argparse.ArgumentParser(
        description="Load scenarios into a SQLite database."
    )
    parser.add_argument(
        "db_path",
        nargs="?",
        type=Path,
        default=questions_db,
        help=f"SQLite file to create or replace (default: {questions_db})",
    )
    args = parser.parse_args()
    load_questions(args.db_path)


if __name__ == "__main__":
    main()
