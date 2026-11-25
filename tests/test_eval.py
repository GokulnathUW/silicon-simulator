"""Tests for eval question sampling."""

from eval.runs import SAMPLE_SEED, sample_questions


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
