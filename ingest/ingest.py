"""Download Twin-2K-500 and load personas, questions, and answers into SQLite."""

import json
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
from huggingface_hub import snapshot_download

from sqlite import write_rows_to_table

REPO_ID = "LLM-Digital-Twin/Twin-2K-500"

# Top-level folders in the Twin-2K-500 dataset repo.
DATASET_FOLDERS = (
    "full_persona",
    "question_catalog_and_human_response_csv",
    "wave_split",
    "raw_data",
    "LLM_simulation_results",
)

# Qualtrics Demographics block. Other answers stay in the questions table.
_DEMO_QIDS = {
    "QID11": "region",
    "QID12": "gender",
    "QID13": "age_band",
    "QID14": "education_level",
    "QID15": "race",
    "QID16": "us_citizen",
    "QID17": "marital_status",
    "QID18": "religion",
    "QID19": "religious_attendance",
    "QID20": "political_affiliation",
    "QID21": "income_band",
    "QID22": "political_views",
    "QID23": "household_size",
    "QID24": "employment_status",
}

_PERSONA_COLUMNS = (
    "persona_id",
    "persona_summary",
    *_DEMO_QIDS.values(),
    "source_revision",
)

_QUESTION_COLUMNS = (
    "item_id",
    "question_id",
    "sub_id",
    "question_text",
    "item_text",
    "question_type",
    "options_json",
    "is_overlap",
    "category",
)

_ANSWER_COLUMNS = (
    "persona_id",
    "item_id",
    "value_numeric",
    "value_label",
)


def download_dataset_folder(folder: str, dest_dir: str | Path) -> Path:
    """Download one Twin-2K-500 folder into dest_dir and return its path.
    Raises:
        ValueError: if folder is not one of DATASET_FOLDERS.
    """

    # Check if the folder is valid
    if folder not in DATASET_FOLDERS:
        allowed = ", ".join(DATASET_FOLDERS)
        raise ValueError(f"Unknown folder {folder!r}. Expected one of: {allowed}")

    # Skip the download if the folder already exists
    dest = Path(dest_dir).expanduser().resolve()
    downloaded_path = dest / folder
    if downloaded_path.is_dir():
        return downloaded_path

    # Download the folder
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {folder} to {dest}")
    snapshot_download(
        repo_id=REPO_ID,
        repo_type="dataset",
        local_dir=dest,
        allow_patterns=[f"{folder}/**"],
    )
    return downloaded_path


def _convert_to_float(value: object) -> float | None:
    """Return a numbers-CSV code. Blank cells and free-text answers have no number."""
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    return float(number)

########################################################
# Helper functions for personas
########################################################

def _convert_demographic_answer_to_integer(column: str, text: str) -> str | int:
    """Turn a demographics answer into the type the personas table stores."""
    if column == "us_citizen":
        return {"Yes": 1, "No": 0}[text]

    # The top bin has no number. 5 keeps the column sortable.
    if column == "household_size":
        if text == "More than 4":
            return 5
        return int(text) 
    return text


def _read_demographic_columns_from_persona_json(persona_json: str) -> dict[str, str | int]:
    """Read the Demographics block into personas columns."""

    # Get the Demographics block
    blocks = json.loads(persona_json)
    block = next(item for item in blocks if item["BlockName"] == "Demographics")
    by_qid = {question["QuestionID"]: question for question in block["Questions"]}

    values: dict[str, str | int] = {}
    for question_id, column in _DEMO_QIDS.items():
        selected_text = by_qid[question_id]["Answers"]["SelectedText"]
        values[column] = _convert_demographic_answer_to_integer(column, selected_text)
    return values


def _read_persona_rows_from_parquet(full_persona_dir: Path) -> Iterator[tuple[object, ...]]:
    """Read the personas rows from the parquet files."""

    # Read the parquet files
    chunks = sorted((full_persona_dir / "chunks").glob("*.parquet"))
    if not chunks:
        raise FileNotFoundError(f"No parquet files in {full_persona_dir / 'chunks'}")

    for path in chunks:
        chunk_content = pd.read_parquet(path)
        for record in chunk_content.itertuples(index=False):

            # Get the persona's demographics
            demographic_columns = _read_demographic_columns_from_persona_json(record.persona_json)
            yield (
                record.pid,
                record.persona_summary,
                *(demographic_columns[column] for column in _DEMO_QIDS.values()),
            )


def load_personas(
    db_path: str | Path,
    full_persona_dir: str | Path,
    source_revision: str | None = None,
    *,
    replace: bool = False,
) -> int:
    """Insert personas from full_persona parquet.
    Returns
        - how many rows were inserted.
    Raises:
        - FileNotFoundError if chunks/ has no parquet
        - ValueError if no personas were found.
    """

    db_path = Path(db_path).expanduser().resolve()
    full_persona_dir = Path(full_persona_dir).expanduser().resolve()

    # Read the rows from the dataset
    rows = [(*row, source_revision) for row in _read_persona_rows_from_parquet(full_persona_dir)]
    if not rows:
        raise ValueError(f"No personas found under {full_persona_dir}")

    # Write the rows to the personas table
    write_rows_to_table(db_path, "personas", _PERSONA_COLUMNS, rows, replace=replace)
    return len(rows)


########################################################
# Helper functions for questions
########################################################

def _read_question_options(question: dict) -> str | None:
    if question["QuestionType"] == "MC":
        return json.dumps(question["Options"])
    if question["QuestionType"] == "Matrix":
        return json.dumps(question["Columns"])
    return None


def _row_statement_for_sub_item(question: dict, sub_id: str | None) -> str | None:
    """Some questions have multiple statements (sub-items)
    Returns
        - the statement corresponding to the sub_id, or None if no sub-items exist.
    """
    if "Rows" not in question:
        return None
    rows = question["Rows"]
    if "RowsID" not in question:
        return rows[int(sub_id) - 1]
    return rows[question["RowsID"].index(sub_id)]

def _read_question_rows_from_catalog(catalog_dir: Path) -> Iterator[tuple[object, ...]]:
    """Read the questions rows from the catalog.
    Returns
        - an iterator of tuples, each containing the question row data.
    """

    catalog = json.loads((catalog_dir / "question_catalog.json").read_text())

    # Read the wave 4 column names
    wave4_response_path = catalog_dir / "wave4_response.csv"
    wave4_column_names = set(pd.read_csv(wave4_response_path, nrows=0).columns) - {"pid"}

    for question in catalog:
        question_id = question["QuestionID"]
        columns = question["csv_columns"]
        options_json = _read_question_options(question)

        for column in columns:
            is_overlap = 1 if column in wave4_column_names else 0

            prefix = f"{question_id}_"
            sub_id = column[len(prefix) :] if column.startswith(prefix) else None

            yield (
                column,
                question_id,
                sub_id,
                question["QuestionText"],
                _row_statement_for_sub_item(question, sub_id),
                question["QuestionType"],
                options_json,
                is_overlap,
                question["BlockName"],
            )


def load_questions(
    db_path: str | Path,
    catalog_dir: str | Path,
    *,
    replace: bool = False,
) -> int:
    """Insert one questions row per catalog column. Returns how many rows were inserted."""
    db_path = Path(db_path).expanduser().resolve()
    catalog_dir = Path(catalog_dir).expanduser().resolve()

    # Read the rows from the dataset
    rows = list(_read_question_rows_from_catalog(catalog_dir))
    if not rows:
        raise ValueError(f"No questions found under {catalog_dir}")

    # Write the rows to the questions table
    write_rows_to_table(db_path, "questions", _QUESTION_COLUMNS, rows, replace=replace)
    return len(rows)


########################################################
# Helper functions for wave 1-3 answers
########################################################

def _read_wave1_3_answer_rows(catalog_dir: Path) -> Iterator[tuple[object, ...]]:
    """Yield one answers_wave1_3 row per answered person-item cell.
    Returns
        - an iterator of tuples, each containing the answer row data.
    Raises:
        - FileNotFoundError: if either CSV is missing.
    """

    # Check if the numeric and label CSVs exist
    numeric_path = catalog_dir / "wave1_3_response.csv"
    label_path = catalog_dir / "wave1_3_response_label.csv"
    if not numeric_path.is_file():
        raise FileNotFoundError(f"Numeric CSV not found: {numeric_path}")
    if not label_path.is_file():
        raise FileNotFoundError(f"Label CSV not found: {label_path}")

    # Read the numeric answers as numbers and the labels as text.
    numbers = pd.read_csv(numeric_path)
    labels = pd.read_csv(label_path, dtype=str)
    numbers["pid"] = numbers["pid"].astype(str)

    labels = labels.set_index("pid").loc[numbers["pid"]]
    persona_ids = numbers["pid"].tolist()

    for item_id in numbers.columns:
        if item_id == "pid":
            continue

        number_cells = numbers[item_id].tolist()
        label_cells = labels[item_id].tolist()

        for persona_id, raw_numeric, raw_label in zip(
            persona_ids, number_cells, label_cells, strict=True
        ):
            numeric = _convert_to_float(raw_numeric) 
            label = None if pd.isna(raw_label) else raw_label
            if numeric is None and label is None:
                continue
            yield (persona_id, item_id, numeric, label)


def load_answers_wave1_3(
    db_path: str | Path,
    catalog_dir: str | Path,
    *,
    replace: bool = False,
) -> int:
    """Insert wave 1-3 answers from the numeric and label CSVs.
    Returns
        - how many rows were inserted.
    Raises:
        FileNotFoundError: if either CSV is missing
    """
    db_path = Path(db_path).expanduser().resolve()
    catalog_dir = Path(catalog_dir).expanduser().resolve()

    # Read wave1-3 answers from the numeric and label CSVs
    rows = list(_read_wave1_3_answer_rows(catalog_dir))
    if not rows:
        raise ValueError(f"No wave 1-3 answers found under {catalog_dir}")

    # Write the rows to the answers_wave1_3 table
    write_rows_to_table(
        db_path,
        "answers_wave1_3",
        _ANSWER_COLUMNS,
        rows,
        replace=replace,
    )
    return len(rows)


########################################################
# Helper functions for wave 4 answers
########################################################

def _read_wave4_answer_rows(catalog_dir: Path) -> Iterator[tuple[object, ...]]:
    """Yield one answers_wave4 row per answered person-item cell.
    Returns
        - an iterator of tuples, each containing the answer row data.
    Raises:
        - FileNotFoundError: if either CSV is missing.
    """

    # Check if the numeric and label CSVs exist
    numeric_path = catalog_dir / "wave4_response.csv"
    label_path  = catalog_dir / "wave4_response_label.csv"
    if not numeric_path.is_file():
        raise FileNotFoundError(f"Numeric CSV not found: {numeric_path}")
    if not label_path.is_file():
        raise FileNotFoundError(f"Label CSV not found: {label_path}")

    # Read the numeric answers as numbers and the labels as text.
    numbers = pd.read_csv(numeric_path)
    labels = pd.read_csv(label_path, dtype=str)
    numbers["pid"] = numbers["pid"].astype(str)

    labels = labels.set_index("pid").loc[numbers["pid"]]
    persona_ids = numbers["pid"].tolist()

    for item_id in numbers.columns:
        if item_id == "pid":
            continue

        number_cells = numbers[item_id].tolist()
        label_cells = labels[item_id].tolist()

        for persona_id, raw_numeric, raw_label in zip(
            persona_ids, number_cells, label_cells, strict=True
        ):
            numeric = _convert_to_float(raw_numeric)
            label = None if pd.isna(raw_label) else raw_label
            if numeric is None and label is None:
                continue
            yield (persona_id, item_id, numeric, label)


def load_answers_wave4(
    db_path: str | Path,
    catalog_dir: str | Path,
    *,
    replace: bool = False,
) -> int:
    """Insert wave 4 answers from the numeric and label CSVs.
    Returns
        - how many rows were inserted.
    Raises:
        - FileNotFoundError: if either CSV is missing.
    """
    db_path = Path(db_path).expanduser().resolve()
    catalog_dir = Path(catalog_dir).expanduser().resolve()

    # Read wave4 answers from the numeric and label CSVs
    rows = list(_read_wave4_answer_rows(catalog_dir))
    if not rows:
        raise ValueError(f"No wave 4 answers found under {catalog_dir}")

    # Write the rows to the answers_wave4 table
    write_rows_to_table(
        db_path,
        "answers_wave4",
        _ANSWER_COLUMNS,
        rows,
        replace=replace,
    )
    return len(rows)
