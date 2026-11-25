"""Tests for eval question sampling and stored predictions."""

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from eval.runs import SAMPLE_SEED, run_eval, sample_questions
from tests.helpers import query


class TestSampleQuestions:
    """Tests for the shared question sample."""

    def test_keeps_at_most_two_sub_items_before_sampling(self) -> None:
        """A parent question contributes at most two sub-items, and the draw repeats."""
        questions = [
            {"item_id": "A", "question_id": "A", "sub_id": None},
            {"item_id": "B1", "question_id": "B", "sub_id": "1"},
            {"item_id": "B2", "question_id": "B", "sub_id": "2"},
            {"item_id": "B3", "question_id": "B", "sub_id": "3"},
            {"item_id": "B4", "question_id": "B", "sub_id": "4"},
            {"item_id": "C", "question_id": "C", "sub_id": None},
        ]

        chosen = sample_questions(
            questions, limit=10, max_sub_items=2, seed=SAMPLE_SEED
        )

        again = [
            question["item_id"]
            for question in sample_questions(questions, 10, 2, SAMPLE_SEED)
        ]
        assert [question["item_id"] for question in chosen] == again
        assert [
            question["item_id"] for question in chosen if question["question_id"] == "A"
        ] == ["A"]
        assert [
            question["item_id"] for question in chosen if question["question_id"] == "C"
        ] == ["C"]
        assert (
            len([question for question in chosen if question["question_id"] == "B"])
            == 2
        )


class TestRunEval:
    """Tests for how eval stores a model answer."""

    def test_openai_stores_choice_and_reason(self, tmp_path: Path, monkeypatch) -> None:
        """An OpenAI answer stores the choice and reason, with no probabilities."""
        personas = pd.DataFrame([{"persona_id": "1", "persona": "alpha"}])
        questions = [
            {
                "item_id": "q1",
                "question_type": "score",
                "campaign": "Wave",
                "instructions": "How much do you agree?",
                "criteria": ["low", "high"],
            }
        ]
        labels = pd.DataFrame(
            [{"persona_id": "1", "item_id": "q1", "actual_label": "high"}]
        )
        answer = SimpleNamespace(choice="high", reason="The tone fits.")
        monkeypatch.setattr(
            "eval.runs.run_inference",
            lambda model_name, instructions, state: SimpleNamespace(
                answers={"q1": answer}
            ),
        )
        monkeypatch.setattr("eval.runs.setting_path", lambda name: tmp_path / "eval.db")

        run_eval(personas, questions, "openai_check", "persona", "gpt-test", labels)

        assert query(
            tmp_path / "eval.db",
            "SELECT persona_id, predicted, reason, probabilities FROM eval_openai_check",
        ) == [("1", "high", "The tone fits.", None)]

    def test_typesafe_stores_score_and_probabilities(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A typesafe score answer stores the score and its probabilities."""
        personas = pd.DataFrame([{"persona_id": "1", "persona": "alpha"}])
        questions = [
            {
                "item_id": "q1",
                "question_type": "score",
                "campaign": "Wave",
                "instructions": "How much do you agree?",
                "criteria": ["low", "high"],
            }
        ]
        labels = pd.DataFrame(
            [{"persona_id": "1", "item_id": "q1", "actual_label": "high"}]
        )
        answer = SimpleNamespace(
            type="score",
            score=1.0,
            choice="low",
            probabilities={"low": 0.2, "high": 0.8},
        )
        monkeypatch.setattr(
            "eval.runs.run_inference",
            lambda model_name, instructions, state: SimpleNamespace(
                answers={"q1": answer}
            ),
        )
        monkeypatch.setattr("eval.runs.setting_path", lambda name: tmp_path / "eval.db")

        run_eval(personas, questions, "jev_check", "persona", "jev-latest", labels)

        assert query(
            tmp_path / "eval.db",
            "SELECT persona_id, predicted, reason, probabilities FROM eval_jev_check",
        ) == [("1", 1.0, "Jev does not provide reasons", '{"low": 0.2, "high": 0.8}')]
