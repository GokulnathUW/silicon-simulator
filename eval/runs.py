import json
import random
import re
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from config import setting_path
from ingest.sqlite import connect
from pipeline.inference import run_inference
from pipeline.prepare import create_instructions, create_state, fetch_personas
from pipeline.run import parse_model_response

ROOT = Path(__file__).resolve().parents[1]
EVAL_TABLES = ROOT / "sql" / "eval_tables.sql"
MAX_SUB_ITEMS = 2
SAMPLE_SEED = 30


def collect_personas(
    db_path: str | Path,
    table_name: str,
    filters: str | list[dict[str, object]],
    selected_columns: dict[str, object],
    limit: int | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    """Return persona text and attribute rows, both keyed by persona id."""
    return fetch_personas(
        db_path,
        table_name,
        filters,
        selected_columns,
        limit,
    )


def split_sentences(text: str) -> list[str]:
    """Return the sentences in text.

    The period in U.S. is not a sentence boundary.
    """
    protected = text.replace("U.S.", "U\u0000S\u0000")
    parts = re.split(r"(?<=[.!?])\s+", protected.strip())
    return [
        part.replace("U\u0000S\u0000", "U.S.").strip() for part in parts if part.strip()
    ]


def collect_questions(db_path: str | Path) -> list[dict[str, object]]:
    """Return the wave 4 multiple-choice and matrix questions."""
    with connect(db_path) as conn:
        question_rows = conn.execute(
            """
            SELECT
                q.item_id, q.question_id, q.sub_id, q.question_type,
                q.question_text, q.item_text, q.options_json
            FROM questions AS q
            WHERE LOWER(q.question_type) IN ('mc', 'matrix')
              AND q.is_overlap = 1
            ORDER BY q.item_id
            """
        ).fetchall()
    return _questions_from_rows(question_rows)


def _questions_from_rows(
    question_rows: list[tuple[object, ...]],
) -> list[dict[str, object]]:
    questions: list[dict[str, object]] = []
    for (
        item_id,
        question_id,
        sub_id,
        question_type,
        question_text,
        item_text,
        options_json,
    ) in question_rows:
        options = json.loads(options_json)
        sentences = split_sentences(question_text or "")
        if len(sentences) > 1:
            campaign = " ".join(sentences[:-1])
            ask = sentences[-1]
        else:
            campaign = ""
            ask = (question_text or "").strip()

        # Matrix options are score levels. Multiple choice stays a choice.
        if question_type.lower() == "matrix":
            if item_text:
                ask = f"{ask} {item_text}".strip()
            model_type = "score"
            criteria: object = options
        else:
            model_type = "choice"
            criteria = {
                option: option for option in options
            }  # create_instructions remove empty keys

        questions.append(
            {
                "item_id": item_id,
                "question_id": question_id,
                "sub_id": sub_id,
                "question_type": model_type,
                "campaign": campaign,
                "instructions": ask,
                "criteria": criteria,
            }
        )
    return questions


def sample_questions(
    questions: list[dict[str, object]],
    limit: int,
    max_sub_items: int,
    seed: int,
) -> list[dict[str, object]]:
    """Return up to `limit` items, with at most `max_sub_items` sub-items of one question."""
    if limit <= 0 or not questions:
        return []
    grouped: dict[str, list[dict[str, object]]] = {}
    for question in questions:
        grouped.setdefault(str(question["question_id"]), []).append(question)

    # A question with many sub-items would otherwise dominate the sample.
    rng = random.Random(seed)
    capped: list[dict[str, object]] = []
    for items in grouped.values():
        sub_items = [question for question in items if question.get("sub_id")]
        plain = [question for question in items if not question.get("sub_id")]
        if len(sub_items) > max_sub_items:
            sub_items = rng.sample(sub_items, max_sub_items)
        capped.extend(plain)
        capped.extend(sub_items)

    chosen = capped if len(capped) <= limit else rng.sample(capped, limit)
    return sorted(chosen, key=lambda question: str(question["item_id"]))


def load_labels(
    db_path: str | Path,
    persona_ids: list[str],
) -> dict[tuple[str, str], str]:
    """Return wave 4 labels for these personas, keyed by persona id and item id."""
    if not persona_ids:
        return {}
    placeholders = ", ".join("?" for _ in persona_ids)
    with connect(db_path) as conn:
        answer_rows = conn.execute(
            f"""
            SELECT a.persona_id, a.item_id, a.value_label
            FROM answers_wave4 AS a
            JOIN questions AS q ON q.item_id = a.item_id
            WHERE LOWER(q.question_type) IN ('mc', 'matrix')
              AND q.is_overlap = 1
              AND a.persona_id IN ({placeholders})
            """,
            persona_ids,
        ).fetchall()
    return {(persona_id, item_id): label for persona_id, item_id, label in answer_rows}


def calculate_accuracy(
    predicted: object,
    actual_label: object | None,
    options: list[str],
    question_type: str,
) -> float | None:
    """Return 1 - abs(model answer - human answer) / answer range.

    Answers are positions on the option list, and the range is its length minus one.
    """
    if question_type == "score":
        model_answer = float(predicted)
    elif str(predicted) in options:
        model_answer = float(options.index(str(predicted)))
    else:
        return None

    answer_range = len(options) - 1
    if answer_range <= 0 or actual_label is None or str(actual_label) not in options:
        return None
    human_answer = options.index(str(actual_label))
    return 1 - abs(model_answer - human_answer) / answer_range


def run_eval(
    personas: pd.DataFrame,
    questions: list[dict[str, object]],
    table_name: str,
    persona_column: str,
    model_name: str,
    labels: pd.DataFrame,
) -> list[dict[str, object]]:
    """Return each persona's answer, store the rows, and print accuracy."""
    table_name = f"eval_{table_name}"
    people = personas.copy()
    people["persona_id"] = people["persona_id"].astype(str)
    labels = labels.astype({"persona_id": str, "item_id": str})
    label_by_item = {
        (str(row.persona_id), str(row.item_id)): row.actual_label
        for row in labels.itertuples(index=False)
    }

    results: list[dict[str, object]] = []
    predictions: list[dict[str, object]] = []
    accuracies: list[float] = []

    print(f"Model: {model_name}", flush=True)
    print(f"Experiment: {table_name}", flush=True)
    pairs = [
        (persona, question)
        for _, persona in personas.iterrows()
        for question in questions
    ]
    for persona, question in tqdm(pairs, desc=table_name):
        persona_id = str(persona["persona_id"])
        persona_text = str(persona[persona_column])
        item_id = str(question["item_id"])

        # Prepare input
        state = create_state(persona_text, str(question["campaign"]))
        instructions = create_instructions(
            0,
            [
                {
                    "id": 0,
                    "question_name": item_id,
                    "question_type": question["question_type"],
                    "instructions": question["instructions"],
                    "criteria": question["criteria"],
                }
            ],
        )

        # Run inference
        response = run_inference(model_name, instructions, state)
        answer = response.answers[item_id]

        # Process the prediction and its accuracy.
        options = [str(option) for option in question["criteria"]]
        question_type = str(question["question_type"])
        predicted, reason = parse_model_response(model_name, answer)
        if model_name.startswith("gpt"):
            probabilities = None
            accuracy_type = "choice"
        else:
            probabilities = json.dumps(
                {str(level): value for level, value in answer.probabilities.items()}
            )
            accuracy_type = question_type

        # Calculate accuracy
        row_accuracy = calculate_accuracy(
            predicted,
            label_by_item.get((persona_id, item_id)),
            options,
            accuracy_type,
        )
        if row_accuracy is not None:
            accuracies.append(row_accuracy)

        # Store the prediction
        predictions.append(
            {
                "persona_id": persona_id,
                "item_id": item_id,
                "predicted": predicted,
                "reason": reason,
                "probabilities": probabilities,
            }
        )
        results.append(
            {"persona_id": persona_id, "item_id": item_id, "response": response}
        )

    # Store the results
    frame = pd.DataFrame(
        predictions,
        columns=["persona_id", "item_id", "predicted", "reason", "probabilities"],
    )
    frame = frame.merge(people, on="persona_id", how="left").merge(
        labels, on=["persona_id", "item_id"], how="left"
    )

    accuracy = sum(accuracies) / len(accuracies) if accuracies else None
    eval_path = setting_path("SIMULATION_DB")
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(eval_path) as conn:
        # Create the eval tables, and add accuracy when an older eval_runs lacks it.
        conn.executescript(EVAL_TABLES.read_text())
        columns = [row[1] for row in conn.execute("PRAGMA table_info(eval_runs)")]
        if "accuracy" not in columns:
            conn.execute("ALTER TABLE eval_runs ADD COLUMN accuracy REAL")
        frame.to_sql(table_name, conn, if_exists="append", index=False)
        eval_id = conn.execute(
            "SELECT COALESCE(MAX(eval_id), 0) + 1 FROM eval_runs"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO eval_runs (
                eval_id, name, model_name, persona_limit, status, accuracy
            ) VALUES (?, ?, ?, ?, 'success', ?)
            """,
            (eval_id, table_name, model_name, len(personas), accuracy),
        )

    if accuracy is not None:
        print(f"{table_name}: accuracy {accuracy:.4f}", flush=True)

    return results
