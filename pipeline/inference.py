"""Ask the model how a persona would answer campaign questions."""

from typesafe_sdk import (
    Choice,
    Noul,
    NoulCriteria,
    Score,
    SystemOneResponse,
    TypeSafeClient,
)


def run_inference(
    model_name: str,
    instructions: list[dict[str, object]],
    state: dict[str, str],
) -> SystemOneResponse:
    """Return the model's answers for one persona and campaign."""

    # Each instruction becomes the matching typesafe question.
    questions: dict[str, Noul | Choice | Score] = {}
    for item in instructions:
        question_type = str(item["question_type"]).lower()
        prompt = item["instructions"]
        criteria = item["criteria"]

        if question_type == "noul":
            question = Noul(
                instructions=prompt,
                criteria=NoulCriteria(true=criteria["true"], false=criteria["false"]),
            )

        elif question_type == "choice":
            question = Choice(instructions=prompt, criteria=criteria)

        else:
            question = Score(instructions=prompt, criteria=criteria)
        questions[str(item["question_name"])] = question

    # Run inference
    with TypeSafeClient() as client:
        return client.system_one(state=state, questions=questions, model=model_name)
