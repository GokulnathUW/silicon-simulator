"""Unit tests for model inference."""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from typesafe_sdk import Choice, Noul, Score

from pipeline.inference import run_inference
from pipeline.prepare import create_instructions


def instruction(
    name: object,
    question_type: object,
    prompt: object,
    criteria: object,
) -> dict[str, object]:
    """Return one inference instruction."""
    return {
        "question_name": name,
        "question_type": question_type,
        "instructions": prompt,
        "criteria": criteria,
    }


@contextmanager
def patched_client(response: object) -> Iterator[MagicMock]:
    """Patch TypeSafeClient and yield the client used for the call."""
    with patch("pipeline.inference.TypeSafeClient") as client_cls:
        client = client_cls.return_value
        client.__enter__.return_value = client
        client.__exit__.return_value = None
        client.system_one.return_value = response
        yield client


class TestRunInference:
    """Tests for run_inference."""

    def test_builds_noul_choice_and_score_questions(self) -> None:
        """Each instruction becomes the matching question in one client call."""
        state = {"persona": "alpha", "campaign": "launch"}
        instructions = [
            instruction(
                "like",
                "Noul",
                {"question": "Do you?"},
                {"true": "yes", "false": "no", "maybe": "skip"},
            ),
            instruction("pick", "Choice", "Which one?", {"A": "first", "B": "second"}),
            instruction("rate", "SCORE", "Rate it", ["low", "high"]),
        ]
        sentinel = object()

        with patched_client(sentinel) as client:
            result = run_inference("jev", instructions, state)

        assert result is sentinel
        client.__enter__.assert_called_once()
        client.__exit__.assert_called_once()
        client.system_one.assert_called_once()
        assert client.system_one.call_args.kwargs["state"] is state
        assert client.system_one.call_args.kwargs["model"] == "jev"
        questions = client.system_one.call_args.kwargs["questions"]
        assert list(questions) == ["like", "pick", "rate"]
        assert isinstance(questions["like"], Noul)
        assert questions["like"].instructions == {"question": "Do you?"}
        assert questions["like"].criteria == {"true": "yes", "false": "no"}
        assert isinstance(questions["pick"], Choice)
        assert questions["pick"].instructions == "Which one?"
        assert questions["pick"].criteria == {"A": "first", "B": "second"}
        assert isinstance(questions["rate"], Score)
        assert questions["rate"].instructions == "Rate it"
        assert list(questions["rate"].criteria) == ["low", "high"]

    @pytest.mark.parametrize(
        "question_type", ["noun", "noul ", "choice ", "score ", "", None, "box"]
    )
    def test_unrecognized_type_becomes_a_score(self, question_type: object) -> None:
        """Only noul and choice select their own question. Everything else is a score."""
        instructions = [instruction("q", question_type, "Rate it", ["low", "high"])]

        with patched_client(object()) as client:
            run_inference("jev", instructions, {"persona": "p", "campaign": "c"})

        question = client.system_one.call_args.kwargs["questions"]["q"]
        assert isinstance(question, Score)

    def test_duplicate_names_keep_the_last_question(self) -> None:
        """A repeated question name replaces the earlier question."""
        instructions = [
            instruction("q", "noul", "first", {"true": "yes", "false": "no"}),
            instruction("q", "choice", "second", {"A": "first"}),
        ]

        with patched_client(object()) as client:
            run_inference("jev", instructions, {"persona": "p", "campaign": "c"})

        question = client.system_one.call_args.kwargs["questions"]["q"]
        assert isinstance(question, Choice)
        assert question.instructions == "second"

    def test_question_name_is_stringified(self) -> None:
        """Numeric names are used as text keys."""
        instructions = [instruction(3, "choice", "Which one?", {"A": "first"})]

        with patched_client(object()) as client:
            run_inference("jev", instructions, {"persona": "p", "campaign": "c"})

        questions = client.system_one.call_args.kwargs["questions"]
        assert list(questions) == ["3"]

    def test_empty_instructions_send_no_questions(self) -> None:
        """An empty instruction list still makes one call."""
        with patched_client(object()) as client:
            run_inference("jev", [], {"persona": "p", "campaign": "c"})

        assert client.system_one.call_args.kwargs["questions"] == {}

    def test_client_errors_propagate(self) -> None:
        """A client failure is raised after the client context closes."""
        instructions = [instruction("q", "choice", "Which one?", {"A": "first"})]

        with patched_client(object()) as client:
            client.system_one.side_effect = RuntimeError("down")
            with pytest.raises(RuntimeError, match="down"):
                run_inference("jev", instructions, {"persona": "p", "campaign": "c"})

        client.__exit__.assert_called_once()

    @pytest.mark.parametrize(
        "criteria",
        [
            {"false": "no"},
            {"true": "yes"},
            {},
        ],
    )
    def test_noul_requires_true_and_false(self, criteria: dict[str, str]) -> None:
        """A noul question reads both criterion labels before calling the client."""
        instructions = [instruction("q", "noul", "Do you?", criteria)]

        with patched_client(object()) as client, pytest.raises(KeyError):
            run_inference("jev", instructions, {"persona": "p", "campaign": "c"})

        client.system_one.assert_not_called()

    def test_choice_requires_a_mapping(self) -> None:
        """A choice question rejects a list of criteria."""
        instructions = [instruction("q", "choice", "Which one?", ["A", "B"])]

        with patched_client(object()) as client, pytest.raises(ValidationError):
            run_inference("jev", instructions, {"persona": "p", "campaign": "c"})

        client.system_one.assert_not_called()

    @pytest.mark.parametrize("criteria", [[], {"A": "first"}])
    def test_score_requires_a_non_empty_sequence(self, criteria: object) -> None:
        """A score question needs one or more rubric levels."""
        instructions = [instruction("q", "score", "Rate it", criteria)]

        with patched_client(object()) as client, pytest.raises(ValidationError):
            run_inference("jev", instructions, {"persona": "p", "campaign": "c"})

        client.system_one.assert_not_called()

    def test_prepared_instructions_build_sdk_questions(self) -> None:
        """Instructions from prepare are accepted for all three question types."""
        questions = [
            {
                "id": 1,
                "question_name": "like",
                "question_type": "noul",
                "instructions": "Do you like it?",
                "focus": "tone",
                "criteria": {"true": "yes", "false": "no"},
            },
            {
                "id": 2,
                "question_name": "pick",
                "question_type": "choice",
                "instructions": "Which ad?",
                "criteria": {"A": "first", "B": "second"},
            },
            {
                "id": 3,
                "question_name": "rate",
                "question_type": "score",
                "instructions": "Rate it",
                "criteria": ["low", "high"],
            },
        ]
        prepared = create_instructions(4, questions)

        with patched_client(object()) as client:
            run_inference("jev", prepared, {"persona": "alpha", "campaign": "launch"})

        built = client.system_one.call_args.kwargs["questions"]
        assert isinstance(built["like"], Noul)
        assert isinstance(built["pick"], Choice)
        assert isinstance(built["rate"], Score)
        assert built["like"].instructions == prepared[0]["instructions"]
        assert built["like"].criteria == prepared[0]["criteria"]
        assert built["pick"].criteria == prepared[1]["criteria"]
        assert list(built["rate"].criteria) == prepared[2]["criteria"]

    def test_blank_noul_criterion_is_removed_before_the_client(self) -> None:
        """An empty noul label is cleaned away, so the client is never called."""
        questions = [
            {
                "id": 1,
                "question_name": "like",
                "question_type": "noul",
                "instructions": "Do you like it?",
                "criteria": {"true": "yes", "false": ""},
            }
        ]
        prepared = create_instructions(1, questions)

        assert prepared[0]["criteria"] == {"true": "yes"}
        with (
            patched_client(object()) as client,
            pytest.raises(KeyError, match="false"),
        ):
            run_inference("jev", prepared, {"persona": "alpha", "campaign": "launch"})

        client.system_one.assert_not_called()
