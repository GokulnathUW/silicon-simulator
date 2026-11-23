"""Run a simulation from the submitted inputs."""

import json
import sqlite3
from pathlib import Path

import pandas as pd

from ingest.sqlite import connect, connect_sqlalchemy
from pipeline.inference import run_inference
from pipeline.prepare import (
    create_instructions,
    create_state,
    fetch_personas,
    prepare_campaign_info,
    prepare_question_info,
)

SIMULATION_TABLES = (
    Path(__file__).resolve().parents[1] / "sql" / "simulation_tables.sql"
)


def persist_simulation(
    conn: sqlite3.Connection,
    simulation_id: int,
    simulation_name: str,
    model_name: str,
    status: str,
) -> None:
    """Record a simulation run or update its outcome."""
    if status == "running":
        conn.execute(
            """
            INSERT INTO simulations (simulation_id, simulation_name, model_name, status)
            VALUES (?, ?, ?, ?)
            """,
            (simulation_id, simulation_name, model_name, status),
        )
    else:
        conn.execute(
            "UPDATE simulations SET status = ? WHERE simulation_id = ?",
            (status, simulation_id),
        )


def run_simulation(
    persona_db: str | Path,
    simulation_db: str | Path,
    simulation_name: str,
    model_name: str,
    persona_table: str,
    filters: str | list[dict[str, object]],
    selected_columns: dict[str, object],
    campaigns: list[dict[str, object]],
    limit: int | None = None,
) -> None:
    """Read personas from persona_db and write the simulation to simulation_db."""
    personas_path = Path(persona_db).expanduser().resolve()
    simulation_path = Path(simulation_db).expanduser().resolve()
    simulation_path.parent.mkdir(parents=True, exist_ok=True)

    # Persist full simulation setup
    with connect_sqlalchemy(simulation_path) as conn:
        transaction = None
        try:
            raw = conn.connection.driver_connection
            # Create the simulation tables when they are not already there.
            raw.executescript(SIMULATION_TABLES.read_text())
            transaction = conn.begin()

            # Next simulation id.
            simulation_id = raw.execute("SELECT COALESCE(MAX(simulation_id), 0) + 1 FROM simulations").fetchone()[0]

            # Persist this run as in progress.
            persist_simulation(raw, simulation_id, simulation_name, model_name, "running")

            # Persist unsaved campaigns.
            campaign_info_df = prepare_campaign_info(raw, campaigns)
            unsaved_campaigns = campaign_info_df.loc[campaign_info_df["is_saved"] != 1]

            if not unsaved_campaigns.empty:
                unsaved_campaigns.to_sql("campaigns", conn, if_exists="append", index=False)

            # Add campaign ids to the campaigns.
            campaign_ids = campaign_info_df["id"].tolist()
            for campaign_id, campaign in zip(campaign_ids, campaigns, strict=True):
                campaign["id"] = campaign_id

            # Persist the simulation-campaign relationships.
            simulation_campaigns_df = pd.DataFrame({"simulation_id": simulation_id, "campaign_id": campaign_info_df["id"]})
            simulation_campaigns_df.to_sql("simulation_campaigns", conn, if_exists="append", index=False)

            question_info_df = prepare_question_info(raw, campaigns)

            campaign_questions_df = question_info_df.loc[
                :, ["campaign_id", "id"]
            ].rename(columns={"id": "question_id"})

            unsaved_questions = (
                question_info_df.loc[question_info_df["is_saved"] == 0]
                .drop(columns=["campaign_id"])
                .assign(
                    criteria=lambda df: df["criteria"].map(
                        lambda v: v if isinstance(v, str) else json.dumps(v)
                    )
                )
            )

            if not unsaved_questions.empty:
                unsaved_questions.to_sql("questions", conn, if_exists="append", index=False)


            # Persist the campaign-question relationships.
            campaign_questions_df.to_sql("campaign_questions", conn, if_exists="append", index=False)

            transaction.commit()
        except Exception:
            if transaction is not None and transaction.is_active:
                transaction.rollback()
            raise

    try:
        # Load the personas for this simulation.
        personas, responses_by_persona = fetch_personas(
            personas_path, persona_table, filters, selected_columns, limit
        )

        # Simulate the responses for each persona for each campaign.
        for campaign in campaigns:
            instructions = create_instructions(campaign["id"], campaign["questions"])
            for persona_id, persona in personas.items():
                state = create_state(persona, campaign["description"])
                simulated_responses = run_inference(model_name, instructions, state)
                row = responses_by_persona[persona_id]
                for instruction in instructions:
                    answer = simulated_responses.answers[instruction["question_name"]]
                    if answer.type == "noul":
                        value = answer.noul # value is probability of true
                    elif answer.type == "choice":
                        value = answer.choice # value is the chosen answer
                    else:
                        value = answer.score # value is the weighted score of the reaction (sum(score * p(score)))
                    row[instruction["question_column_name"]] = value

        # Save the responses, then mark the simulation successful.
        with connect(simulation_path) as conn:
            pd.DataFrame(list(responses_by_persona.values())).to_sql(
                simulation_name, conn, if_exists="append", index=False
            )
            persist_simulation(conn, simulation_id, simulation_name, model_name, "success")
    except Exception:
        with connect(simulation_path) as conn:
            persist_simulation(conn, simulation_id, simulation_name, model_name, "failure")
        raise
