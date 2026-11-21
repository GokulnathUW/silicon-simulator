"""Create the Twin-2K-500 SQLite database"""

import argparse
from pathlib import Path

from ingest import (
    download_dataset_folder,
    load_answers_wave1_3,
    load_answers_wave4,
    load_personas,
    load_questions,
)
from sqlite import apply_schema, table_exists

CATALOG_FOLDER = "question_catalog_and_human_response_csv"


def create_database(download_dir: str | Path, db_path: str | Path) -> None:
    """Fill a SQLite database from Twin-2K-500"""
    download_dir = Path(download_dir).expanduser().resolve()
    db_path = Path(db_path).expanduser().resolve()

    # Check if any tables are missing
    personas_missing  = not table_exists(db_path, "personas")
    questions_missing = not table_exists(db_path, "questions")
    wave1_3_missing   = not table_exists(db_path, "answers_wave1_3")
    wave4_missing     = not table_exists(db_path, "answers_wave4")

    if not download_dir.exists():
        download_dir.mkdir(parents=True)

    if personas_missing:
        apply_schema(db_path)
        persona_dir = download_dataset_folder("full_persona", download_dir)
        count = load_personas(db_path, persona_dir)
        print(f"Loaded {count} personas")

    if questions_missing:
        apply_schema(db_path)
        catalog_dir = download_dataset_folder(CATALOG_FOLDER, download_dir)
        count = load_questions(db_path, catalog_dir)
        print(f"Loaded {count} questions")

    if wave1_3_missing or wave4_missing:
        apply_schema(db_path)
        catalog_dir = download_dataset_folder(CATALOG_FOLDER, download_dir)
        if wave1_3_missing:
            count = load_answers_wave1_3(db_path, catalog_dir)
            print(f"Loaded {count} wave 1-3 answers")
        if wave4_missing:
            count = load_answers_wave4(db_path, catalog_dir)
            print(f"Loaded {count} wave 4 answers")


def main() -> None:
    """Read the download folder and database path, then create the database."""
    parser = argparse.ArgumentParser(description="Create the Twin-2K-500 SQLite database.")
    parser.add_argument("download_dir", type=Path, help="Folder for the downloaded dataset")
    parser.add_argument("db_path", type=Path, help="SQLite database to create or fill")
    args = parser.parse_args()
    create_database(args.download_dir, args.db_path)


if __name__ == "__main__":
    main()