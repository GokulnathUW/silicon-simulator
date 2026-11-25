"""Tests for the persona texts used in the ablation."""

from eval.ablation import big_five_text, demographic_text

SUMMARY = """The following is a description of a person.

The person's demographics are the following...
Gender: Female
Age: 30-49

The person's Big 5 scores are the following:
score_extraversion = 2

The person's need for cognition score is the following:
score_needforcognition = 3
"""


class TestAblationPersonas:
    """Tests for the persona text sections."""

    def test_demographic_text_stops_before_big_five(self) -> None:
        """Demographics keep the opening and leave out later scores."""
        text = demographic_text(SUMMARY)

        assert text.startswith("The following is a description of a person.")
        assert "Gender: Female" in text
        assert "score_extraversion" not in text

    def test_big_five_text_stops_before_the_next_score(self) -> None:
        """Big Five keeps its scores and leaves out the next section."""
        text = big_five_text(SUMMARY)

        assert "score_extraversion = 2" in text
        assert "score_needforcognition" not in text
        assert "Gender: Female" not in text
