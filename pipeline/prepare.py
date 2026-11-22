"""Prepare the inputs for a simulation."""

import sqlite3
from pathlib import Path

import pandas as pd

from ingest.sqlite import connect, table_exists
from prompts.system_prompt import SYSTEM_PROMPT


def fetch_personas(
    db_path: str | Path,
    table_name: str,
    filters: str | list[dict[str, object]],
    selected_columns: dict[str, object],
) -> tuple[dict[object, dict[str, object]], dict[object, dict[str, object]]]:
    """Return personas keyed by persona id, and a response row for each persona."""

    # Check if table exists
    if not table_exists(db_path, table_name):
        raise ValueError(f"Table {table_name} does not exist")

    # Get the columns we need for the output
    id_column = selected_columns.get("id")
    persona_column = selected_columns.get("persona_column")
    other_columns = selected_columns.get("other_columns")
    if not isinstance(id_column, str) or not isinstance(persona_column, str):
        raise TypeError("selected_columns needs id and persona_column")

    output_columns: list[str] = [id_column, persona_column, *other_columns]
    output_columns = list(set(output_columns))

    quoted_output = ", ".join(f'"{name}"' for name in output_columns)
    sql = f'SELECT {quoted_output} FROM "{table_name}"'

    # Apply the filters
    params: list[object] = []
    clauses: list[str] = []

    # One condition per filter. The row must satisfy all of them.
    if filters:
        for filter in filters:
            column = filter["columns"]
            filter_type = filter["type"]
            values = filter["values"]

            if filter_type == "single_select":
                value = values
                if isinstance(values, list):
                    value = values[0]
                clauses.append(f"{column} = ?")
                params.append(value)

            elif filter_type == "multi_select":
                placeholders = ", ".join("?" for _ in values)
                clauses.append(f"{column} IN ({placeholders})")
                params.extend(values)

            elif filter_type == "slider":
                clauses.append(f"{column} BETWEEN ? AND ?")
                params.extend(values)

    if clauses:
        sql = f"{sql} WHERE {' AND '.join(clauses)}"

    with connect(db_path) as conn:
        personas_df = pd.read_sql_query(sql, conn, params=params)

    # persona_id keys both lookups. The response row leaves out the persona text.
    personas_df = personas_df.rename(columns={id_column: "persona_id"})
    personas = {row["persona_id"]: row[persona_column] for _, row in personas_df.iterrows()}

    persona_with_columns = {
        row["persona_id"]: row
        for row in personas_df.drop(columns=[persona_column]).to_dict(orient="records")
    }
    return personas, persona_with_columns


def prepare_campaign_info(
    conn: sqlite3.Connection,
    campaigns: list[dict[str, object]],
) -> pd.DataFrame:
    """Return the campaign rows for this simulation."""
    next_campaign_id = conn.execute(
        "SELECT COALESCE(MAX(id), 0) + 1 FROM campaigns"
    ).fetchone()[0]
    campaign_ids: list[int] = []

    # Generate new campaign ids for unsaved campaigns
    for campaign in campaigns:
        if campaign["is_saved"] == 1:
            campaign_ids.append(campaign["id"])
        else:
            campaign_ids.append(next_campaign_id)
            next_campaign_id += 1

    # Build the campaign rows
    return pd.DataFrame(
        {
            "id": campaign_ids,
            "name": [campaign["name"] for campaign in campaigns],
            "description": [campaign["description"] for campaign in campaigns],
            "is_saved": [campaign["is_saved"] for campaign in campaigns],
        }
    )


def prepare_question_info(
    conn: sqlite3.Connection,
    campaigns: list[dict[str, object]],
) -> pd.DataFrame:
    """Return the question rows for this simulation."""

    # All questions
    questions = [
        (campaign["id"], question)
        for campaign in campaigns
        for question in campaign["questions"]
    ]

    next_question_id = conn.execute(
        "SELECT COALESCE(MAX(id), 0) + 1 FROM questions"
    ).fetchone()[0]
    question_ids: list[int] = []

    # Generate new question ids for unsaved questions
    for _campaign_id, question in questions:
        if question["is_saved"] == 1:
            question_ids.append(question["id"])
        else:
            question_ids.append(next_question_id)
            next_question_id += 1

    return pd.DataFrame(
        {
            "id": question_ids,
            "campaign_id": [campaign_id for campaign_id, _question in questions],
            "question_name": [question["question_name"] for _, question in questions],
            "question_type": [question["question_type"] for _, question in questions],
            "instructions": [question["instructions"] for _, question in questions],
            "criteria": [question["criteria"] for _, question in questions],
            "is_saved": [question["is_saved"] for _, question in questions],
        }
    )


def create_state(persona: str, campaign: str) -> dict[str, str]:
    """Return one persona's state for one campaign."""
    # TODO: Add retrieval to enrich persona
    return {"persona": persona, "campaign": campaign}


def _remove_empty_keys(value: dict[str, object]) -> dict[str, object]:
    """Return a copy of value without empty keys."""
    cleaned: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            item = _remove_empty_keys(item)
        if item is None or item == "" or item == {} or item == []:
            continue
        cleaned[key] = item
    return cleaned


def create_instructions(
    campaign_id: int,
    questions: list[dict[str, object]],
) -> list[dict[str, object]]:
    prepared: list[dict[str, object]] = []
    for question in questions:
        prepared.append(
            _remove_empty_keys(
                {
                    "id": question["id"],
                    "question_name": question["question_name"],
                    "question_type": question["question_type"],
                    "question_column_name": f"camp_{campaign_id}_ques{question['id']}",  # simulation result table uses this as column name
                    "instructions": {
                        "question": f"{SYSTEM_PROMPT}\n{question['instructions']}",
                        "focus": question.get("focus"),
                        "inspect": "`campaign`",
                    },
                    "criteria": question["criteria"],
                }
            )
        )
    return prepared
