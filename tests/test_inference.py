"""Unit tests for model inference."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from typesafe_sdk import Choice, Noul, Score

from pipeline import inference
from pipeline.inference import run_chatgpt_inference, run_inference
from pipeline.prepare import create_instructions
from prompts.system_prompt import SYSTEM_PROMPT


def instruction(
    name: object,
    question_type: object,
    question: object,
    criteria: object,
) -> dict[str, object]:
    """Return one inference instruction."""
    return {
        "question_name": name,
        "question_type": question_type,
        "instructions": {
            "system_prompt": SYSTEM_PROMPT,
            "question": question,
        },
        "criteria": criteria,
    }


@contextmanager
def patched_client(response: object) -> Iterator[MagicMock]:
    """Patch the shared client and yield the client used for the call."""
    inference._client = None
    with patch("pipeline.inference.TypeSafeClient") as client_cls:
        client = client_cls.return_value
        client.system_one.return_value = response
        try:
            yield client
        finally:
            inference._client = None


class TestRunInference:
    """Tests for run_inference."""

    def test_builds_noul_choice_and_score_questions(self) -> None:
        """Each instruction becomes the matching question in one client call."""
        state = {"persona": "alpha", "campaign": "launch"}
        instructions = [
            instruction(
                "like",
                "Noul",
                "Do you?",
                {"true": "yes", "false": "no", "maybe": "skip"},
            ),
            instruction("pick", "Choice", "Which one?", {"A": "first", "B": "second"}),
            instruction("rate", "SCORE", "Rate it", ["low", "high"]),
        ]
        sentinel = object()

        with patched_client(sentinel) as client:
            result = run_inference("jev", instructions, state)

        assert result is sentinel
        client.system_one.assert_called_once()
        assert client.system_one.call_args.kwargs["state"] is state
        assert client.system_one.call_args.kwargs["model"] == "jev"
        questions = client.system_one.call_args.kwargs["questions"]
        assert list(questions) == ["like", "pick", "rate"]
        assert isinstance(questions["like"], Noul)
        assert questions["like"].instructions == {
            "question": f"{SYSTEM_PROMPT}\nDo you?"
        }
        assert questions["like"].criteria == {"true": "yes", "false": "no"}
        assert isinstance(questions["pick"], Choice)
        assert questions["pick"].instructions == {
            "question": f"{SYSTEM_PROMPT}\nWhich one?"
        }
        assert questions["pick"].criteria == {"A": "first", "B": "second"}
        assert isinstance(questions["rate"], Score)
        assert questions["rate"].instructions == {
            "question": f"{SYSTEM_PROMPT}\nRate it"
        }
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
        assert question.instructions == {"question": f"{SYSTEM_PROMPT}\nsecond"}

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

    def test_repeated_calls_share_one_client(self) -> None:
        """A later call uses the client created for the first call."""
        instructions = [instruction("q", "choice", "Which one?", {"A": "first"})]
        state = {"persona": "p", "campaign": "c"}

        with patched_client(object()) as client:
            run_inference("jev", instructions, state)
            run_inference("jev", instructions, state)
            assert inference.TypeSafeClient.call_count == 1

        assert client.system_one.call_count == 2
        sent = [
            call.kwargs["questions"]["q"].instructions
            for call in client.system_one.call_args_list
        ]
        assert sent[0] == sent[1] == {"question": f"{SYSTEM_PROMPT}\nWhich one?"}

    def test_client_errors_propagate(self) -> None:
        """A client failure is raised."""
        instructions = [instruction("q", "choice", "Which one?", {"A": "first"})]

        with patched_client(object()) as client:
            client.system_one.side_effect = RuntimeError("down")
            with pytest.raises(RuntimeError, match="down"):
                run_inference("jev", instructions, {"persona": "p", "campaign": "c"})

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
        assert built["like"].instructions == {
            "question": f"{SYSTEM_PROMPT}\nDo you like it?",
            "focus": "tone",
            "inspect": "`campaign`",
        }
        assert prepared[0]["instructions"]["system_prompt"] == SYSTEM_PROMPT
        assert prepared[0]["instructions"]["question"] == "Do you like it?"
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


def test_chatgpt_inference_calls_once_per_question() -> None:
    """Each question is one ChatGPT call, and the model is created once."""
    instructions = [
        {
            "question_name": "like",
            "question_type": "noul",
            "instructions": {
                "system_prompt": SYSTEM_PROMPT,
                "question": "Do you like it?",
                "inspect": "`campaign`",
            },
            "criteria": {"true": "yes", "false": "no"},
        },
        {
            "question_name": "pick",
            "question_type": "choice",
            "instructions": {"question": "Which ad?"},
            "criteria": ["first", "second"],
        },
    ]
    state = {"persona": "alpha", "campaign": "launch"}
    original = json.loads(json.dumps(instructions))
    raw = SimpleNamespace(
        usage_metadata={"input_tokens": 11, "output_tokens": 3},
        response_metadata={"model_name": "chatgpt-test"},
    )
    inference._chatgpt_models.clear()
    with patch("pipeline.inference.ChatOpenAI") as chat_cls:
        structured = chat_cls.return_value.with_structured_output.return_value
        structured.invoke.side_effect = [
            {
                "raw": raw,
                "parsed": inference._Answer(choice="yes", reason="The tone fits."),
                "parsing_error": None,
            },
            {
                "raw": raw,
                "parsed": inference._Answer(choice="first", reason="It is familiar."),
                "parsing_error": None,
            },
        ]
        try:
            result = run_chatgpt_inference("chatgpt-test", instructions, state)
        finally:
            inference._chatgpt_models.clear()

    assert chat_cls.call_count == 1
    assert result.model == "chatgpt-test"
    assert result.usage.input_tokens == 22
    assert result.usage.output_tokens == 6
    assert result.answers["like"].choice == "yes"
    assert result.answers["like"].reason == "The tone fits."
    assert result.answers["pick"].choice == "first"
    assert chat_cls.call_args.kwargs == {
        "model": "chatgpt-test",
        "use_responses_api": True,
    }
    schema_call = chat_cls.return_value.with_structured_output.call_args
    assert schema_call.args == (inference._Answer,)
    assert schema_call.kwargs == {"include_raw": True}
    assert structured.invoke.call_count == 2
    first_system, first_user = structured.invoke.call_args_list[0].args[0]
    second_system, second_user = structured.invoke.call_args_list[1].args[0]
    assert first_system.content == second_system.content == SYSTEM_PROMPT
    assert first_user.content == (
        "Persona:\nalpha\n\n"
        "Campaign:\nlaunch\n\n"
        "Question:\nDo you like it?\n\n"
        "Options:\ntrue: yes\nfalse: no"
    )
    assert second_user.content == (
        "Persona:\nalpha\n\n"
        "Campaign:\nlaunch\n\n"
        "Question:\nWhich ad?\n\n"
        "Options:\nfirst\nsecond"
    )
    assert instructions == original


def test_chatgpt_model_is_reused_for_the_same_name() -> None:
    """A later persona reuses the model. A different name creates another one."""
    instructions = [
        {
            "question_name": "like",
            "question_type": "noul",
            "instructions": {"question": "Do you like it?"},
            "criteria": {"true": "yes", "false": "no"},
        }
    ]
    state = {"persona": "alpha", "campaign": "launch"}
    raw = SimpleNamespace(
        usage_metadata={"input_tokens": 1, "output_tokens": 1},
        response_metadata={"model_name": "chatgpt-test"},
    )
    inference._chatgpt_models.clear()
    with patch("pipeline.inference.ChatOpenAI") as chat_cls:
        chat_cls.return_value.with_structured_output.return_value.invoke.return_value = {
            "raw": raw,
            "parsed": inference._Answer(choice="yes", reason="Because."),
            "parsing_error": None,
        }
        try:
            run_chatgpt_inference("chatgpt-test", instructions, state)
            run_chatgpt_inference("chatgpt-test", instructions, state)
            assert chat_cls.call_count == 1
            run_chatgpt_inference("chatgpt-other", instructions, state)
            assert chat_cls.call_count == 2
        finally:
            inference._chatgpt_models.clear()
