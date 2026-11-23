"""Load the demo questions and run them on three personas.

python scripts/run_demo.py
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from load_questions import load_questions

from config import setting, setting_path
from pipeline.run import run_simulation

SELECTED_COLUMNS = {
    "id": "persona_id",
    "persona_column": "persona_summary",
    "other_columns": ["region", "gender", "age_band"],
}

MAX_PERSONAS = 3


def reaction_questions(db_path: Path) -> list[dict[str, object]]:
    """Return the score questions stored in the reactions table."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name, instructions_json, criteria_json
            FROM reactions
            ORDER BY rowid
            """
        ).fetchall()

    questions: list[dict[str, object]] = []
    for name, instructions_json, criteria_json in rows:
        instructions = json.loads(instructions_json)
        questions.append(
            {
                "question_name": name,
                "question_type": "score",
                "instructions": instructions["question"],
                "focus": instructions["focus"],
                "criteria": json.loads(criteria_json),
                "is_saved": 0,
            }
        )
    return questions


def parse_campaigns(db_path: Path) -> list[dict[str, object]]:
    """Return one campaign per loaded question row.

    A score row is an advertisement. Its questions are the shared reactions.
    A noul or choice row is one campaign with one question.
    """
    reactions = reaction_questions(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT category, campaign, instructions_json, criteria_json
            FROM questions
            ORDER BY rowid
            """
        ).fetchall()

    campaigns: list[dict[str, object]] = []
    next_question_id = 1
    ad_number = 0
    for category, campaign, instructions_json, criteria_json in rows:
        if category == "score":
            ad_number += 1
            questions: list[dict[str, object]] = []
            for reaction in reactions:
                question = dict(reaction)
                question["id"] = next_question_id
                next_question_id += 1
                questions.append(question)
            name = f"ad {ad_number}"
        else:
            instructions = json.loads(instructions_json)
            questions = [
                {
                    "id": next_question_id,
                    "question_name": instructions["question"],
                    "question_type": category,
                    "instructions": instructions["question"],
                    "focus": instructions["focus"],
                    "criteria": json.loads(criteria_json),
                    "is_saved": 0,
                }
            ]
            next_question_id += 1
            name = str(instructions["question"])

        campaigns.append(
            {
                "name": name,
                "description": campaign,
                "is_saved": 0,
                "questions": questions,
            }
        )
    return campaigns


def run_demo(questions_db: Path, persona_db: Path, model_name: str) -> None:
    """Load the demo questions and ask up to three personas to answer them."""
    started = time.perf_counter()

    print(f"Loading questions into {questions_db}", flush=True)
    load_started = time.perf_counter()
    load_questions(questions_db)
    load_seconds = time.perf_counter() - load_started
    print(f"Loaded questions in {load_seconds:.1f}s", flush=True)

    print(f"Parsing campaigns from {questions_db}", flush=True)
    parse_started = time.perf_counter()
    campaigns = parse_campaigns(questions_db)
    parse_seconds = time.perf_counter() - parse_started
    question_count = sum(len(campaign["questions"]) for campaign in campaigns)
    print(
        f"Parsed {len(campaigns)} campaigns and {question_count} questions "
        f"in {parse_seconds:.1f}s",
        flush=True,
    )
    for campaign in campaigns:
        print(
            f"  {campaign['name']}: {len(campaign['questions'])} questions",
            flush=True,
        )

    simulation_db = setting_path("SIMULATION_DB")
    simulation_name = setting("SIMULATION_NAME")
    persona_table = setting("PERSONA_TABLE")
    calls = MAX_PERSONAS * len(campaigns)
    print(
        f"Running {simulation_name} with {model_name} on up to {MAX_PERSONAS} "
        f"personas ({calls} model calls)",
        flush=True,
    )
    print(f"Reading personas from {persona_db}", flush=True)
    print(f"Writing results to {simulation_db}", flush=True)
    run_started = time.perf_counter()
    run_simulation(
        persona_db,
        simulation_db,
        simulation_name,
        model_name,
        persona_table,
        [],
        SELECTED_COLUMNS,
        campaigns,
        MAX_PERSONAS,
    )
    run_seconds = time.perf_counter() - run_started
    total_seconds = time.perf_counter() - started
    print(f"Simulation finished in {run_seconds:.1f}s", flush=True)
    print(
        "Timing\n"
        f"  load questions    {load_seconds:.1f}s\n"
        f"  parse campaigns   {parse_seconds:.1f}s\n"
        f"  simulation        {run_seconds:.1f}s\n"
        f"  total             {total_seconds:.1f}s",
        flush=True,
    )


def main() -> None:
    """Load the questions database and run it on the configured personas."""
    questions_db = setting_path("QUESTIONS_DB")
    persona_db = setting_path("PERSONA_DB")
    model_name = setting("MODEL_NAME")
    parser = argparse.ArgumentParser(
        description="Run the demo questions on three personas."
    )
    parser.add_argument(
        "--questions-db",
        type=Path,
        default=questions_db,
        help=f"Demo questions database (default: {questions_db})",
    )
    parser.add_argument(
        "--persona-db",
        type=Path,
        default=persona_db,
        help=f"Persona database (default: {persona_db})",
    )
    parser.add_argument(
        "--model",
        default=model_name,
        help=f"Model name (default: {model_name})",
    )
    args = parser.parse_args()
    run_demo(args.questions_db, args.persona_db, args.model)


if __name__ == "__main__":
    main()
