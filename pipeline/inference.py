"""Ask the model how a persona would answer campaign questions."""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from typesafe_sdk import (
    Choice,
    Noul,
    NoulCriteria,
    Score,
    SystemOneResponse,
    TypeSafeClient,
)

from config import load_env
from prompts.system_prompt import SYSTEM_PROMPT

_typesafe_client: TypeSafeClient | None = None
_chatgpt_model: ChatOpenAI | None = None


class OpenAIQuestionResponse(BaseModel):
    """One question's structured answer."""

    choice: str
    reason: str


class _Usage(BaseModel):
    """Token counts reported for one ChatGPT call."""

    input_tokens: int | None = None
    output_tokens: int | None = None


class _ChatgptResponse(BaseModel):
    """ChatGPT answers for one persona and campaign."""

    model: str
    usage: _Usage
    answers: dict[str, OpenAIQuestionResponse]


def get_typesafe_client() -> TypeSafeClient:
    """Return the shared client, creating it the first time it is needed."""
    global _typesafe_client
    if _typesafe_client is None:
        load_env()
        _typesafe_client = TypeSafeClient()
    return _typesafe_client


def get_chatgpt_model(model_name: str) -> ChatOpenAI:
    """Return the ChatGPT model for this name, creating it the first time."""
    global _chatgpt_model
    if _chatgpt_model is None:
        load_env()
        _chatgpt_model = ChatOpenAI(model=model_name, use_responses_api=True)
    return _chatgpt_model


def run_inference(
    model_name: str,
    instructions: list[dict[str, object]],
    state: dict[str, str],
) -> SystemOneResponse | _ChatgptResponse:
    """Return the model's answers for one persona and campaign."""
    if model_name.startswith("jev"):
        return run_jev_inference(model_name, instructions, state)
    if model_name.startswith("gpt"):
        return run_chatgpt_inference(model_name, instructions, state)
    raise ValueError(f"Unsupported model: {model_name}")


def run_jev_inference(
    model_name: str,
    instructions: list[dict[str, object]],
    state: dict[str, str],
) -> SystemOneResponse:
    """Return Jev's answers for one persona and campaign."""

    # Each instruction becomes the matching typesafe question.
    questions: dict[str, Noul | Choice | Score] = {}
    for item in instructions:
        question_type = str(item["question_type"]).lower()
        # Copy so a later persona still sees the original system prompt.
        prompt = dict(item["instructions"])
        system_prompt = prompt.pop("system_prompt")
        question = prompt["question"]
        prompt["question"] = f"{system_prompt}\n{question}"
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

    return get_typesafe_client().system_one(
        state=state, questions=questions, model=model_name
    )


def run_chatgpt_inference(
    model_name: str,
    instructions: list[dict[str, object]],
    state: dict[str, str],
) -> _ChatgptResponse:
    """Return ChatGPT's answers for one persona and campaign."""
    model_structured_output = get_chatgpt_model(model_name).with_structured_output(OpenAIQuestionResponse, include_raw=True)
    persona = state["persona"]
    campaign = state["campaign"]

    answers: dict[str, OpenAIQuestionResponse] = {}
    input_tokens: int | None = None
    output_tokens: int | None = None
    reported_model = model_name

    for item in instructions:

        # Build options for the question
        criteria = item.get("criteria")
        if isinstance(criteria, dict):
            options = "\n".join(f"{key}: {value}" for key, value in criteria.items())
        elif isinstance(criteria, list):
            options = "\n".join(str(option) for option in criteria)
        else:
            options = "" if criteria is None else str(criteria)

        # Build user prompt
        user_prompt = f"Campaign: {campaign}\nQuestion: {item['instructions']['question']}\nOptions: {options}"

        # Invoke the model
        result = model_structured_output.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                ("developer", f"Persona: {persona}"),
                HumanMessage(content=user_prompt),
            ]
        )

        # Handle errors
        if result["parsing_error"] is not None:
            raise result["parsing_error"]

        raw = result["raw"]
        usage = raw.usage_metadata or {}
        if usage.get("input_tokens") is not None:
            input_tokens = (input_tokens or 0) + usage["input_tokens"]
        if usage.get("output_tokens") is not None:
            output_tokens = (output_tokens or 0) + usage["output_tokens"]
        reported_model = raw.response_metadata.get("model_name") or reported_model
        answers[str(item["question_name"])] = result["parsed"]

    return _ChatgptResponse(
        model=reported_model,
        usage=_Usage(input_tokens=input_tokens, output_tokens=output_tokens),
        answers=answers,
    )
