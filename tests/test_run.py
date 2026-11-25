"""Unit tests for simulation runs and their saved status."""

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import sqlalchemy.exc

from ingest.sqlite import connect
from pipeline import inference
from pipeline.inference import OpenAIQuestionResponse
from pipeline.prepare import create_instructions
from pipeline.run import parse_model_response, persist_simulation, run_simulation
from tests.helpers import apply_simulation_schema, query, write_table

SELECTED = {
    "id": "persona_id",
    "persona_column": "persona_summary",
    "other_columns": ["age", "region"],
}
WEST_ADULTS = [
    {"columns": "age", "type": "slider", "values": [25, 45]},
    {"columns": "region", "type": "multi_select", "values": ["West"]},
]
PEOPLE = [
    (1, "alpha", 30, "West"),
    (2, "beta", 50, "East"),
    (3, "gamma", 40, "West"),
]


def people_db(path: Path, rows: list[tuple[object, ...]] | None = None) -> Path:
    """Create a persona table and return its database path."""
    write_table(
        path,
        "people",
        ["persona_id", "persona_summary", "age", "region"],
        PEOPLE if rows is None else rows,
    )
    return path


def noul_question(
    question_id: int, *, saved: int = 0, name: str = "like"
) -> dict[str, object]:
    """Return a noul question with both labels filled in."""
    return {
        "id": question_id,
        "question_name": name,
        "question_type": "noul",
        "instructions": "Do you like it?",
        "criteria": {"true": "yes", "false": "no"},
        "is_saved": saved,
    }


def answer_response(
    instructions: list[dict[str, object]], value: object
) -> SimpleNamespace:
    """Return a response with one value for every instruction."""
    answers = {}
    for item in instructions:
        question_type = item["question_type"]
        if question_type == "noul":
            answers[item["question_name"]] = SimpleNamespace(type="noul", noul=value)
        elif question_type == "choice":
            answers[item["question_name"]] = SimpleNamespace(
                type="choice", choice=value
            )
        else:
            answers[item["question_name"]] = SimpleNamespace(type="score", score=value)
    return SimpleNamespace(answers=answers)


class TestParseModelResponse:
    """Tests for parse_model_response."""

    def test_typesafe_uses_the_field_for_the_answer_type(self) -> None:
        """A typesafe answer stores noul, choice, or score."""
        assert parse_model_response("jev", SimpleNamespace(type="noul", noul=0.4)) == (
            0.4,
            None,
        )
        assert parse_model_response(
            "jev", SimpleNamespace(type="choice", choice="A")
        ) == ("A", None)
        assert parse_model_response(
            "jev", SimpleNamespace(type="score", score=2.5)
        ) == (2.5, None)

    def test_openai_stores_the_choice_and_reason(self) -> None:
        """A ChatGPT answer stores the choice and the reason."""
        answer = SimpleNamespace(choice="yes", reason="The tone fits.")
        assert parse_model_response("openai-test", answer) == (
            "yes",
            "The tone fits.",
        )


class TestPersistSimulation:
    """Tests for persist_simulation."""

    def test_running_inserts_a_row(self, simulation_db: Path) -> None:
        """A running simulation is inserted with its name and model."""
        with connect(simulation_db) as conn:
            persist_simulation(conn, 1, "Launch one", "jev", "running")

        assert query(
            simulation_db,
            "SELECT simulation_id, simulation_name, model_name, status FROM simulations",
        ) == [(1, "Launch one", "jev", "running")]

    @pytest.mark.parametrize(
        "status", ["success", "failure", "RUNNING", "running ", "", None]
    )
    def test_other_statuses_update_an_existing_row(
        self, simulation_db: Path, status: object
    ) -> None:
        """Anything other than running updates the status and leaves the rest of the row."""
        with connect(simulation_db) as conn:
            persist_simulation(conn, 1, "Launch one", "jev", "running")
        with connect(simulation_db) as conn:
            persist_simulation(conn, 1, "Renamed", "other-model", status)

        assert query(
            simulation_db,
            "SELECT simulation_id, simulation_name, model_name, status FROM simulations",
        ) == [(1, "Launch one", "jev", status)]

    def test_update_without_a_row_does_nothing(self, simulation_db: Path) -> None:
        """Updating a missing simulation does not create one."""
        with connect(simulation_db) as conn:
            persist_simulation(conn, 99, "Launch one", "jev", "success")

        assert query(simulation_db, "SELECT COUNT(*) FROM simulations") == [(0,)]

    def test_second_running_insert_is_rejected(self, simulation_db: Path) -> None:
        """A simulation id cannot be inserted twice."""
        with connect(simulation_db) as conn:
            persist_simulation(conn, 1, "Launch one", "jev", "running")

        with pytest.raises(sqlite3.IntegrityError), connect(simulation_db) as conn:
            persist_simulation(conn, 1, "Launch one", "jev", "running")

        assert query(simulation_db, "SELECT status FROM simulations") == [("running",)]


class TestRunSimulation:
    """Tests for run_simulation."""

    def test_chatgpt_run_stores_choice_and_reason(self, tmp_path: Path) -> None:
        """A ChatGPT run stores each question's choice and reason."""
        persona_db = people_db(tmp_path / "personas.db", [(1, "alpha", 30, "West")])
        simulation_db = tmp_path / "simulations.db"
        campaign = {
            "name": "Launch",
            "description": "Ad A's launch",
            "is_saved": 0,
            "questions": [noul_question(1)],
        }
        raw = SimpleNamespace(
            usage_metadata={"input_tokens": 5, "output_tokens": 2},
            response_metadata={"model_name": "chatgpt-test"},
        )
        inference._chatgpt_model = None
        with patch("pipeline.inference.ChatOpenAI") as chat:
            chat.return_value.with_structured_output.return_value.invoke.return_value = {
                "raw": raw,
                "parsed": OpenAIQuestionResponse(choice="yes", reason="The tone fits."),
                "parsing_error": None,
            }
            try:
                run_simulation(
                    persona_db,
                    simulation_db,
                    "launch",
                    "openai-test",
                    "people",
                    [],
                    SELECTED,
                    [campaign],
                )
            finally:
                inference._chatgpt_model = None

        assert query(simulation_db, "SELECT model_name, status FROM simulations") == [
            ("openai-test", "success")
        ]
        assert query(
            simulation_db,
            "SELECT persona_id, camp_1_ques1, camp_1_ques1_reason FROM launch",
        ) == [(1, "yes", "The tone fits.")]

    def test_persists_setup_and_answers(self, tmp_path: Path) -> None:
        """A run saves the setup, asks for every persona and campaign, and stores answers."""
        persona_db = people_db(tmp_path / "personas.db")
        simulation_db = tmp_path / "simulations.db"
        like = {
            "id": 1,
            "question_name": "like",
            "question_type": "noul",
            "instructions": "Do you like it?",
            "criteria": {"true": "likes José", "false": "does not"},
            "focus": "tone",
            "is_saved": 0,
        }
        pick = {
            "id": 2,
            "question_name": "pick",
            "question_type": "choice",
            "instructions": "Which ad?",
            "criteria": {"A": "first", "B": "second"},
            "focus": "",
            "is_saved": 0,
        }
        rate = {
            "id": 3,
            "question_name": "rate",
            "question_type": "score",
            "instructions": "Rate it",
            "criteria": ["low", "high"],
            "is_saved": 0,
        }
        campaigns = [
            {
                "name": "Launch",
                "description": "Ad A's launch",
                "is_saved": 0,
                "questions": [like, pick],
            },
            {
                "name": "Follow up",
                "description": "Second ad",
                "is_saved": 0,
                "questions": [rate],
            },
        ]
        seen: list[tuple[str, list[dict[str, object]], dict[str, str]]] = []
        values = {
            ("alpha", "noul"): 0.0,
            ("alpha", "choice"): "",
            ("alpha", "score"): 0,
            ("gamma", "noul"): 1.0,
            ("gamma", "choice"): "B",
            ("gamma", "score"): 5,
        }

        def fake(
            model_name: str,
            instructions: list[dict[str, object]],
            state: dict[str, str],
        ) -> SimpleNamespace:
            seen.append((model_name, instructions, state))
            answers = {}
            for item in instructions:
                question_type = str(item["question_type"])
                value = values[(state["persona"], question_type)]
                if question_type == "noul":
                    answers[item["question_name"]] = SimpleNamespace(
                        type="noul", noul=value
                    )
                elif question_type == "choice":
                    answers[item["question_name"]] = SimpleNamespace(
                        type="choice", choice=value
                    )
                else:
                    answers[item["question_name"]] = SimpleNamespace(
                        type="score", score=value
                    )
            return SimpleNamespace(answers=answers)

        with (
            patch("pipeline.run.run_inference", side_effect=fake),
            patch(
                "pipeline.run.persist_simulation", wraps=persist_simulation
            ) as persist,
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "Launch one",
                "jev",
                "people",
                WEST_ADULTS,
                SELECTED,
                campaigns,
            )

        assert [call.args[4] for call in persist.call_args_list] == [
            "running",
            "success",
        ]
        assert [state["persona"] for _, _, state in seen] == [
            "alpha",
            "gamma",
            "alpha",
            "gamma",
        ]
        assert [state["campaign"] for _, _, state in seen] == [
            "Ad A's launch",
            "Ad A's launch",
            "Second ad",
            "Second ad",
        ]
        assert {model for model, _, _ in seen} == {"jev"}
        assert (
            seen[0][1]
            == seen[1][1]
            == create_instructions(1, campaigns[0]["questions"])
        )
        assert (
            seen[2][1]
            == seen[3][1]
            == create_instructions(2, campaigns[1]["questions"])
        )
        assert [item["question_column_name"] for item in seen[0][1]] == [
            "camp_1_ques1",
            "camp_1_ques2",
        ]
        assert [item["question_column_name"] for item in seen[2][1]] == ["camp_2_ques3"]
        assert campaigns[0]["id"] == 1
        assert campaigns[1]["id"] == 2

        assert query(
            simulation_db,
            "SELECT simulation_id, simulation_name, model_name, status FROM simulations",
        ) == [(1, "Launch one", "jev", "success")]
        assert query(
            simulation_db,
            "SELECT id, name, description, is_saved FROM campaigns ORDER BY id",
        ) == [
            (1, "Launch", "Ad A's launch", 0),
            (2, "Follow up", "Second ad", 0),
        ]
        assert query(
            simulation_db,
            """
            SELECT id, question_name, question_type, instructions, criteria, is_saved
            FROM questions
            ORDER BY id
            """,
        ) == [
            (1, "like", "noul", "Do you like it?", json.dumps(like["criteria"]), 0),
            (2, "pick", "choice", "Which ad?", json.dumps(pick["criteria"]), 0),
            (3, "rate", "score", "Rate it", json.dumps(rate["criteria"]), 0),
        ]
        assert query(
            simulation_db,
            "SELECT simulation_id, campaign_id FROM simulation_campaigns ORDER BY campaign_id",
        ) == [
            (1, 1),
            (1, 2),
        ]
        assert query(
            simulation_db,
            "SELECT campaign_id, question_id FROM campaign_questions ORDER BY question_id",
        ) == [
            (1, 1),
            (1, 2),
            (2, 3),
        ]
        assert query(
            simulation_db,
            """
            SELECT COUNT(*) FROM simulations
            WHERE created_at IS NULL OR created_at = ''
            """,
        ) == [(0,)]
        columns = [
            row[1] for row in query(simulation_db, 'PRAGMA table_info("Launch one")')
        ]
        assert set(columns) == {
            "persona_id",
            "age",
            "region",
            "camp_1_ques1",
            "camp_1_ques1_reason",
            "camp_1_ques2",
            "camp_1_ques2_reason",
            "camp_2_ques3",
            "camp_2_ques3_reason",
        }
        assert [column for column in columns if str(column).startswith("camp_")] == [
            "camp_1_ques1",
            "camp_1_ques1_reason",
            "camp_1_ques2",
            "camp_1_ques2_reason",
            "camp_2_ques3",
            "camp_2_ques3_reason",
        ]
        assert query(
            simulation_db,
            """
            SELECT persona_id, age, region, camp_1_ques1, camp_1_ques2, camp_2_ques3
            FROM "Launch one"
            ORDER BY persona_id
            """,
        ) == [
            (1, 30, "West", 0.0, "", 0),
            (3, 40, "West", 1.0, "B", 5),
        ]

    def test_reuses_saved_records_and_generates_ids_for_new_ones(
        self, simulation_db: Path, tmp_path: Path
    ) -> None:
        """Saved rows stay as they are. New rows get the next ids, and answers use the input question id."""
        persona_db = people_db(tmp_path / "personas.db", [(1, "alpha", 30, "West")])
        with connect(simulation_db) as conn:
            conn.execute(
                """
                INSERT INTO campaigns (id, name, description, is_saved)
                VALUES (4, 'Saved campaign', 'Existing offer', 1)
                """
            )
            conn.execute(
                """
                INSERT INTO questions (
                    id, question_name, question_type, instructions, criteria, is_saved
                )
                VALUES (9, 'kept', 'score', 'Rate the saved one', '["low","high"]', 1)
                """
            )
        fresh = {
            "id": 100,
            "question_name": "fresh",
            "question_type": "noul",
            "instructions": "New question",
            "criteria": {"true": "yes", "false": "no"},
            "is_saved": 0,
        }
        saved = {
            "id": 9,
            "question_name": "ignored",
            "question_type": "score",
            "instructions": "ignored instructions",
            "criteria": ["nope"],
            "is_saved": 1,
        }
        campaigns = [
            {
                "id": 77,
                "name": "New",
                "description": "New offer",
                "is_saved": 0,
                "questions": [fresh],
            },
            {
                "id": 4,
                "name": "Ignored rename",
                "description": "Ignored description",
                "is_saved": 1,
                "questions": [saved],
            },
        ]
        seen: list[dict[str, str]] = []

        def fake(
            _model_name: str,
            instructions: list[dict[str, object]],
            state: dict[str, str],
        ) -> SimpleNamespace:
            seen.append(state)
            return answer_response(
                instructions, 0.4 if instructions[0]["question_type"] == "noul" else 3
            )

        with patch("pipeline.run.run_inference", side_effect=fake):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert [campaign["id"] for campaign in campaigns] == [5, 4]
        assert fresh["id"] == 100
        assert [state["campaign"] for state in seen] == [
            "New offer",
            "Ignored description",
        ]
        assert query(
            simulation_db,
            "SELECT id, name, description, is_saved FROM campaigns ORDER BY id",
        ) == [
            (4, "Saved campaign", "Existing offer", 1),
            (5, "New", "New offer", 0),
        ]
        assert query(
            simulation_db,
            "SELECT id, question_name, instructions, criteria, is_saved FROM questions ORDER BY id",
        ) == [
            (9, "kept", "Rate the saved one", '["low","high"]', 1),
            (10, "fresh", "New question", json.dumps(fresh["criteria"]), 0),
        ]
        assert query(
            simulation_db,
            "SELECT simulation_id, campaign_id FROM simulation_campaigns ORDER BY campaign_id",
        ) == [
            (1, 4),
            (1, 5),
        ]
        assert query(
            simulation_db,
            "SELECT campaign_id, question_id FROM campaign_questions ORDER BY campaign_id",
        ) == [
            (4, 9),
            (5, 10),
        ]
        columns = [row[1] for row in query(simulation_db, "PRAGMA table_info(launch)")]
        assert set(columns) == {
            "persona_id",
            "age",
            "region",
            "camp_5_ques100",
            "camp_5_ques100_reason",
            "camp_4_ques9",
            "camp_4_ques9_reason",
        }
        assert [column for column in columns if str(column).startswith("camp_")] == [
            "camp_5_ques100",
            "camp_5_ques100_reason",
            "camp_4_ques9",
            "camp_4_ques9_reason",
        ]
        assert query(
            simulation_db, "SELECT camp_5_ques100, camp_4_ques9 FROM launch"
        ) == [(0.4, 3)]

    def test_string_and_null_criteria_are_stored_as_json_text(
        self, tmp_path: Path
    ) -> None:
        """Text criteria stay as they are. Every other value is stored with json.dumps."""
        persona_db = people_db(tmp_path / "personas.db", [(1, "alpha", 30, "West")])
        simulation_db = tmp_path / "simulations.db"
        campaigns = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 0,
                "questions": [
                    {
                        "id": 1,
                        "question_name": "already",
                        "question_type": "score",
                        "instructions": "Rate it",
                        "criteria": '["low","high"]',
                        "is_saved": 0,
                    },
                    {
                        "id": 2,
                        "question_name": "missing",
                        "question_type": "score",
                        "instructions": "Rate it",
                        "criteria": None,
                        "is_saved": 0,
                    },
                ],
            }
        ]

        def fake(
            _model_name: str,
            instructions: list[dict[str, object]],
            _state: dict[str, str],
        ) -> SimpleNamespace:
            return SimpleNamespace(
                answers={
                    item["question_name"]: SimpleNamespace(type="score", score=1)
                    for item in instructions
                }
            )

        with patch("pipeline.run.run_inference", side_effect=fake):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert query(
            simulation_db, "SELECT id, criteria FROM questions ORDER BY id"
        ) == [
            (1, '["low","high"]'),
            (2, "null"),
        ]

    def test_empty_campaign_list_still_saves_persona_rows(self, tmp_path: Path) -> None:
        """A simulation with no campaigns records the selected personas and does not call the model."""
        persona_db = people_db(tmp_path / "personas.db", [(1, "alpha", 30, "West")])
        simulation_db = tmp_path / "simulations.db"

        with patch("pipeline.run.run_inference") as inference:
            run_simulation(
                persona_db, simulation_db, "launch", "jev", "people", [], SELECTED, []
            )

        inference.assert_not_called()
        assert query(simulation_db, "SELECT status FROM simulations") == [("success",)]
        assert query(simulation_db, "SELECT COUNT(*) FROM campaigns") == [(0,)]
        assert query(simulation_db, "SELECT persona_id, age, region FROM launch") == [
            (1, 30, "West")
        ]

    def test_campaign_with_no_questions_calls_the_model_with_no_instructions(
        self,
        tmp_path: Path,
    ) -> None:
        """Each persona is still evaluated when a campaign has no questions."""
        persona_db = people_db(tmp_path / "personas.db", [(1, "alpha", 30, "West")])
        simulation_db = tmp_path / "simulations.db"
        campaigns = [
            {"name": "Launch", "description": "Offer", "is_saved": 0, "questions": []}
        ]
        seen: list[list[dict[str, object]]] = []

        def fake(
            _model_name: str,
            instructions: list[dict[str, object]],
            _state: dict[str, str],
        ) -> SimpleNamespace:
            seen.append(instructions)
            return SimpleNamespace(answers={})

        with patch("pipeline.run.run_inference", side_effect=fake):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert seen == [[]]
        assert query(simulation_db, "SELECT COUNT(*) FROM questions") == [(0,)]
        assert query(simulation_db, "SELECT COUNT(*) FROM campaign_questions") == [(0,)]
        assert query(simulation_db, "SELECT persona_id FROM launch") == [(1,)]

    def test_non_choice_answers_use_the_score_field(self, tmp_path: Path) -> None:
        """An answer that is neither noul nor choice is read from its score field."""
        persona_db = people_db(tmp_path / "personas.db", [(1, "alpha", 30, "West")])
        simulation_db = tmp_path / "simulations.db"
        campaigns = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 0,
                "questions": [
                    {
                        "id": 1,
                        "question_name": "rate",
                        "question_type": "score",
                        "instructions": "Rate it",
                        "criteria": ["low", "high"],
                        "is_saved": 0,
                    }
                ],
            }
        ]
        response = SimpleNamespace(
            answers={"rate": SimpleNamespace(type="box", score=2.5)}
        )

        with patch("pipeline.run.run_inference", return_value=response):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert query(simulation_db, "SELECT camp_1_ques1 FROM launch") == [(2.5,)]

    def test_reusing_a_campaign_question_pair_is_rejected(self, tmp_path: Path) -> None:
        """The same campaign and question cannot be linked twice, and the first results stay."""
        persona_db = people_db(tmp_path / "personas.db", [(1, "alpha", 30, "West")])
        simulation_db = tmp_path / "simulations.db"
        first = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 0,
                "questions": [noul_question(1)],
            }
        ]
        second = [
            {
                "id": 1,
                "name": "Launch",
                "description": "Offer",
                "is_saved": 1,
                "questions": [noul_question(1, saved=1)],
            }
        ]

        with patch(
            "pipeline.run.run_inference",
            return_value=answer_response([noul_question(1)], 0.25),
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                first,
            )
        with (
            patch("pipeline.run.run_inference") as inference,
            pytest.raises(
                sqlalchemy.exc.IntegrityError, match="UNIQUE constraint failed"
            ),
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                second,
            )

        inference.assert_not_called()
        assert query(
            simulation_db, "SELECT simulation_id, status FROM simulations"
        ) == [(1, "success")]
        assert query(simulation_db, "SELECT COUNT(*) FROM campaigns") == [(1,)]
        assert query(simulation_db, "SELECT COUNT(*) FROM questions") == [(1,)]
        assert query(simulation_db, "SELECT persona_id, camp_1_ques1 FROM launch") == [
            (1, 0.25)
        ]

    def test_second_run_with_new_columns_keeps_the_first_results(
        self, tmp_path: Path
    ) -> None:
        """A new campaign id writes a new column, so appending to the same table fails."""
        persona_db = people_db(tmp_path / "personas.db", [(1, "alpha", 30, "West")])
        simulation_db = tmp_path / "simulations.db"
        campaigns = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 0,
                "questions": [noul_question(1)],
            }
        ]

        with patch(
            "pipeline.run.run_inference",
            return_value=answer_response([noul_question(1)], 0.25),
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )
        with (
            patch(
                "pipeline.run.run_inference",
                return_value=answer_response([noul_question(1)], 0.75),
            ),
            pytest.raises(sqlite3.OperationalError, match="no column"),
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert query(
            simulation_db,
            "SELECT simulation_id, status FROM simulations ORDER BY simulation_id",
        ) == [
            (1, "success"),
            (2, "failure"),
        ]
        assert query(simulation_db, "SELECT COUNT(*) FROM campaigns") == [(2,)]
        assert query(simulation_db, "SELECT camp_1_ques1 FROM launch") == [(0.25,)]

    def test_inference_error_marks_the_run_failed(self, tmp_path: Path) -> None:
        """A model error is stored as a failure and raised again, with no result rows."""
        persona_db = people_db(tmp_path / "personas.db")
        simulation_db = tmp_path / "simulations.db"
        campaigns = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 0,
                "questions": [noul_question(1)],
            }
        ]
        calls = {"count": 0}
        error = RuntimeError("model down")

        def fake(*_args: object) -> SimpleNamespace:
            calls["count"] += 1
            if calls["count"] == 2:
                raise error
            return answer_response([noul_question(1)], 0.5)

        with (
            patch(
                "pipeline.run.persist_simulation", wraps=persist_simulation
            ) as persist,
            patch("pipeline.run.run_inference", side_effect=fake),
            pytest.raises(RuntimeError, match="model down") as raised,
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert raised.value is error
        assert [call.args[4] for call in persist.call_args_list] == [
            "running",
            "failure",
        ]
        assert calls["count"] == 2
        assert query(simulation_db, "SELECT status FROM simulations") == [("failure",)]
        assert (
            query(
                simulation_db,
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'launch'",
            )
            == []
        )

    def test_missing_answer_marks_the_run_failed(self, tmp_path: Path) -> None:
        """A response that omits a question name fails the run."""
        persona_db = people_db(tmp_path / "personas.db", [(1, "alpha", 30, "West")])
        simulation_db = tmp_path / "simulations.db"
        campaigns = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 0,
                "questions": [noul_question(1)],
            }
        ]

        with (
            patch(
                "pipeline.run.run_inference", return_value=SimpleNamespace(answers={})
            ),
            pytest.raises(KeyError),
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert query(simulation_db, "SELECT status FROM simulations") == [("failure",)]

    def test_blank_noul_criterion_marks_the_run_failed(self, tmp_path: Path) -> None:
        """The saved criteria keep the blank label, and the run fails when it is removed for the model."""
        persona_db = people_db(tmp_path / "personas.db", [(1, "alpha", 30, "West")])
        simulation_db = tmp_path / "simulations.db"
        criteria = {"true": "yes", "false": ""}
        campaigns = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 0,
                "questions": [
                    {
                        "id": 1,
                        "question_name": "like",
                        "question_type": "noul",
                        "instructions": "Do you like it?",
                        "criteria": criteria,
                        "is_saved": 0,
                    }
                ],
            }
        ]

        with pytest.raises(KeyError, match="false"):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert query(simulation_db, "SELECT status FROM simulations") == [("failure",)]
        assert query(simulation_db, "SELECT criteria FROM questions") == [
            (json.dumps(criteria),)
        ]

    def test_creates_parent_directories_and_records_a_missing_table(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A new nested database is created, and a missing persona table fails the run."""
        monkeypatch.chdir(tmp_path)
        persona_db = Path("nested") / "personas.db"
        simulation_db = Path("nested") / "simulations.db"
        campaigns = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 0,
                "questions": [noul_question(1)],
            }
        ]

        with pytest.raises(ValueError, match="Table people does not exist"):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        created = tmp_path / simulation_db
        assert created.is_file()
        assert query(
            created, "SELECT simulation_name, model_name, status FROM simulations"
        ) == [("launch", "jev", "failure")]
        assert query(created, "SELECT COUNT(*) FROM campaigns") == [(1,)]

    def test_empty_population_marks_the_run_failed(self, tmp_path: Path) -> None:
        """No matching personas cannot be written as a table with no columns."""
        persona_db = people_db(tmp_path / "personas.db")
        simulation_db = tmp_path / "simulations.db"
        filters = [{"columns": "region", "type": "single_select", "values": "North"}]
        campaigns = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 0,
                "questions": [noul_question(1)],
            }
        ]

        with (
            patch("pipeline.run.run_inference") as inference,
            pytest.raises(sqlite3.OperationalError, match="syntax error"),
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                filters,
                SELECTED,
                campaigns,
            )

        inference.assert_not_called()
        assert query(simulation_db, "SELECT status FROM simulations") == [("failure",)]
        assert (
            query(
                simulation_db,
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'launch'",
            )
            == []
        )

    def test_setup_error_rolls_back_the_simulation(self, tmp_path: Path) -> None:
        """A bad campaign leaves no simulation, campaign, or question rows."""
        persona_db = tmp_path / "personas.db"
        simulation_db = tmp_path / "simulations.db"
        campaigns = [{"description": "Offer", "is_saved": 0, "questions": []}]

        with (
            patch("pipeline.run.run_inference") as inference,
            pytest.raises(KeyError, match="name"),
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        inference.assert_not_called()
        assert query(simulation_db, "SELECT COUNT(*) FROM simulations") == [(0,)]
        assert query(simulation_db, "SELECT COUNT(*) FROM campaigns") == [(0,)]

    def test_question_setup_error_rolls_back_inserted_campaigns(
        self, tmp_path: Path
    ) -> None:
        """A later setup error removes campaign rows written earlier in the transaction."""
        persona_db = tmp_path / "personas.db"
        simulation_db = tmp_path / "simulations.db"
        campaigns = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 0,
                "questions": [{"is_saved": 0}],
            }
        ]

        with pytest.raises(KeyError):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert query(simulation_db, "SELECT COUNT(*) FROM simulations") == [(0,)]
        assert query(simulation_db, "SELECT COUNT(*) FROM campaigns") == [(0,)]

    def test_campaign_saved_flag_outside_zero_and_one_rolls_back(
        self, tmp_path: Path
    ) -> None:
        """A campaign saved flag other than 0 or 1 is rejected and nothing is kept."""
        persona_db = tmp_path / "personas.db"
        simulation_db = tmp_path / "simulations.db"
        campaigns = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 2,
                "questions": [noul_question(1)],
            }
        ]

        with pytest.raises(
            sqlalchemy.exc.IntegrityError, match="CHECK constraint failed"
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert query(simulation_db, "SELECT COUNT(*) FROM simulations") == [(0,)]
        assert query(simulation_db, "SELECT COUNT(*) FROM campaigns") == [(0,)]

    def test_question_saved_flag_outside_zero_and_one_rolls_back(
        self, tmp_path: Path
    ) -> None:
        """A question that is neither saved nor unsaved is not inserted, so the link fails."""
        persona_db = tmp_path / "personas.db"
        simulation_db = tmp_path / "simulations.db"
        question = noul_question(1)
        question["is_saved"] = 2
        campaigns = [
            {
                "name": "Launch",
                "description": "Offer",
                "is_saved": 0,
                "questions": [question],
            }
        ]

        with pytest.raises(
            sqlalchemy.exc.IntegrityError, match="FOREIGN KEY constraint failed"
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert query(simulation_db, "SELECT COUNT(*) FROM simulations") == [(0,)]
        assert query(simulation_db, "SELECT COUNT(*) FROM campaigns") == [(0,)]
        assert query(simulation_db, "SELECT COUNT(*) FROM questions") == [(0,)]

    def test_saved_question_must_already_exist(self, tmp_path: Path) -> None:
        """A saved question id that is not in the database fails the link and rolls back."""
        persona_db = people_db(tmp_path / "personas.db", [(1, "alpha", 30, "West")])
        simulation_db = tmp_path / "simulations.db"
        apply_simulation_schema(simulation_db)
        with connect(simulation_db) as conn:
            conn.execute(
                """
                INSERT INTO campaigns (id, name, description, is_saved)
                VALUES (1, 'Saved', 'Offer', 1)
                """
            )
        campaigns = [
            {
                "id": 1,
                "name": "Saved",
                "description": "Offer",
                "is_saved": 1,
                "questions": [noul_question(99, saved=1)],
            }
        ]

        with pytest.raises(
            sqlalchemy.exc.IntegrityError, match="FOREIGN KEY constraint failed"
        ):
            run_simulation(
                persona_db,
                simulation_db,
                "launch",
                "jev",
                "people",
                [],
                SELECTED,
                campaigns,
            )

        assert query(simulation_db, "SELECT COUNT(*) FROM simulations") == [(0,)]
        assert query(simulation_db, "SELECT id, name FROM campaigns") == [(1, "Saved")]
