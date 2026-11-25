"""Score the full persona summary repeatedly."""

import argparse
from pathlib import Path

import pandas as pd

from config import setting, setting_path
from eval.runs import (
    MAX_SUB_ITEMS,
    SAMPLE_SEED,
    collect_personas,
    collect_questions,
    load_labels,
    run_eval,
    sample_questions,
)
from ingest.sqlite import connect

REPEATS = 5


def run_repeatability(
    persona_db: str | Path,
    model_name: str,
    repeats: int,
    max_personas: int | None = None,
    max_questions: int | None = None,
) -> None:
    """Score the full persona summary once for each repeat."""

    # Get the other columns from the personas table.
    with connect(persona_db) as conn:
        column_names = [
            str(row[1])
            for row in conn.execute('PRAGMA table_info("personas")').fetchall()
        ]
    other_columns = [
        name for name in column_names if name not in {"persona_id", "persona_summary"}
    ]

    # Get the persona texts and attribute rows.
    persona_texts, attribute_rows = collect_personas(
        persona_db,
        "personas",
        [],
        {
            "id": "persona_id",
            "persona_column": "persona_summary",
            "other_columns": other_columns,
        },
        max_personas,
    )
    persona_ids = [str(persona_id) for persona_id in persona_texts]

    # Get the questions and labels.
    questions = collect_questions(persona_db)
    labels = load_labels(persona_db, persona_ids)
    answered = set(labels)

    # Sample items with max 2 per question.
    questions = [
        question
        for question in questions
        if persona_ids
        and all(
            (persona_id, str(question["item_id"])) in answered
            for persona_id in persona_ids
        )
    ]
    questions = sample_questions(
        questions,
        len(questions) if max_questions is None else max_questions,
        MAX_SUB_ITEMS,
        SAMPLE_SEED,
    )

    # Get corresponding labels.
    item_ids = {str(question["item_id"]) for question in questions}
    selected_ids = set(persona_ids)
    labels = {
        (persona_id, item_id): label
        for (persona_id, item_id), label in labels.items()
        if persona_id in selected_ids and item_id in item_ids
    }
    label_frame = pd.DataFrame(
        [
            {
                "persona_id": persona_id,
                "item_id": item_id,
                "actual_label": label,
            }
            for (persona_id, item_id), label in labels.items()
        ],
        columns=["persona_id", "item_id", "actual_label"],
    )

    # The persona text is the full summary on every repeat.
    personas = pd.DataFrame(list(attribute_rows.values()))
    summaries = {
        str(persona_id): str(summary) for persona_id, summary in persona_texts.items()
    }
    personas["persona_id"] = personas["persona_id"].astype(str)
    personas["persona_summary"] = personas["persona_id"].map(summaries)
    personas["persona"] = personas["persona_summary"]

    for repeat in range(1, repeats + 1):
        run_eval(
            personas,
            questions,
            f"repeatability_{repeat}",
            "persona",
            model_name,
            label_frame,
        )


def main() -> None:
    """Run the full-summary repeatability eval."""
    parser = argparse.ArgumentParser(description="Evaluate full-summary repeatability.")
    parser.add_argument(
        "--persona-db",
        type=Path,
        default=setting_path("PERSONA_DB"),
        help="Persona database",
    )
    parser.add_argument(
        "--model",
        default=setting("MODEL_NAME"),
        help="Model name",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=REPEATS,
        help="How many times to score the full summary.",
    )
    parser.add_argument(
        "--max-personas",
        type=int,
        default=None,
        help="Maximum personas to score. Omit for no limit.",
    )
    parser.add_argument(
        "--max-questions",
        type=int,
        default=None,
        help="Maximum questions to score. Omit for no limit.",
    )
    args = parser.parse_args()
    run_repeatability(
        args.persona_db,
        args.model,
        args.repeats,
        args.max_personas,
        args.max_questions,
    )


if __name__ == "__main__":
    main()
