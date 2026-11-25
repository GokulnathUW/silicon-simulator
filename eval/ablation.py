"""Build the persona text variantss used in the ablation."""

import argparse
from collections.abc import Callable
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

INTRO = "The following is a description of a person.\n\n"
DEMOGRAPHIC_HEADING = "The person's demographics are the following"
BIG_FIVE_HEADING = "The person's Big 5 scores are the following"
AFTER_BIG_FIVE_HEADING = "The person's need for cognition score is the following"

CONDITIONS = (
    "no_persona",
    "demographic",
    "big_five",
    "demographic_big_five",
    "scores_only",
    "persona_summary",
)


def section(summary: str, start_heading: str | None, end_heading: str | None) -> str:
    """Return one summary section, including the opening description line."""
    start = summary.find(start_heading) if start_heading else 0
    end = summary.find(end_heading) if end_heading else len(summary)
    if start < 0 or end <= start:
        raise ValueError(f"Persona summary has no {start_heading!r} or {end_heading!r}")
    return INTRO + summary[start:end].strip()


def no_persona_text(summary: str) -> str:
    """Return no persona."""
    return INTRO + "You are a person."


def demographic_text(summary: str) -> str:
    """Return the demographic section of a persona summary."""
    return section(summary, DEMOGRAPHIC_HEADING, BIG_FIVE_HEADING)


def big_five_text(summary: str) -> str:
    """Return the Big Five score section of a persona summary."""
    return section(summary, BIG_FIVE_HEADING, AFTER_BIG_FIVE_HEADING)


def scores_only_text(summary: str) -> str:
    """Return the scores-only section of a persona summary."""
    return section(summary, AFTER_BIG_FIVE_HEADING, None)


def demographic_big_five_text(summary: str) -> str:
    """Return the demographic section followed by the Big Five section."""
    return section(summary, DEMOGRAPHIC_HEADING, AFTER_BIG_FIVE_HEADING)


def persona_summary_text(summary: str) -> str:
    """Return the persona summary unchanged."""
    return summary


FORMATTERS: dict[str, Callable[[str], str]] = {
    "no_persona": no_persona_text,
    "demographic": demographic_text,
    "big_five": big_five_text,
    "demographic_big_five": demographic_big_five_text,
    "scores_only": scores_only_text,
    "persona_summary": persona_summary_text,
}


def run_ablation(
    persona_db: str | Path,
    model_name: str,
    styles: list[str],
    max_personas: int | None = None,
    max_questions: int | None = None,
) -> None:
    """Score the personas under each requested style."""

    # Get the other columns from the personas table.
    with connect(persona_db) as conn:
        column_names = [
            str(row[1])
            for row in conn.execute('PRAGMA table_info("personas")').fetchall()
        ]
    other_columns = [name for name in column_names if name not in {"persona_id", "persona_summary"}]

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

    # Sample items with max 2 per question
    questions = [
        question for question in questions
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

    # Run the eval for each style.
    for style in styles:
        if style not in FORMATTERS:
            raise ValueError(f"Unknown persona style {style!r}")
        formatter = FORMATTERS[style]
        personas = pd.DataFrame(list(attribute_rows.values()))

        # Add the persona summary back to personas.
        summaries = {
            str(persona_id): str(summary) for persona_id, summary in persona_texts.items()
        }
        personas["persona_id"] = personas["persona_id"].astype(str)
        personas["persona_summary"] = personas["persona_id"].map(summaries)
        personas["persona"] = personas["persona_summary"].map(formatter)

        # Run the eval.
        run_eval(
            personas,
            questions,
            f"{model_name}_ablation_{style}",
            "persona",
            model_name,
            label_frame,
        )


def main() -> None:
    """Run the ablation for the requested persona styles."""
    parser = argparse.ArgumentParser(description="Evaluate persona ablations.")
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
        "--styles",
        nargs="*",
        default=list(CONDITIONS),
        help="Persona styles to score",
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
    run_ablation(
        args.persona_db,
        args.model,
        args.styles,
        args.max_personas,
        args.max_questions,
    )


if __name__ == "__main__":
    main()
