"""Yes/no scenarios for a pipeline check."""

from dataclasses import dataclass
from typing import Literal, TypedDict


class NoulInstructions(TypedDict):
    """The question, the state field it reads, and what a yes requires."""

    question: str
    inspect: str
    focus: str


class NoulCriterion(TypedDict):
    """What one outcome covers, what it does not, and an example."""

    what: str
    not_for: str
    examples: list[str]


@dataclass(frozen=True)
class YesNoQuestion:
    """One yes/no campaign and the question about it."""

    campaign: str
    instructions: NoulInstructions
    criteria: dict[str, NoulCriterion]
    category: Literal["noul"] = "noul"


YES_NO_QUESTIONS: tuple[YesNoQuestion, ...] = (
    YesNoQuestion(
        campaign=(
            "Sony is selling the WH-1000XM5 headphones on its website. "
            "The regular price is $400. "
            "This week the headphones are 20% off, which brings the price to $320. "
            "Shipping is free."
        ),
        instructions={
            "question": (
                "Will you buy the Sony WH-1000XM5 headphones this week for $320, "
                "with free shipping?"
            ),
            "inspect": "`campaign`",
            "focus": "Answer yes only if you buy the headphones this week for $320.",
        },
        criteria={
            "true": {
                "what": "This person buys the headphones now and pays $320.",
                "not_for": "This person likes Sony, or plans to buy the headphones later, but does not buy them this week.",
                "examples": [
                    "This person orders the headphones this week and pays $320."
                ],
            },
            "false": {
                "what": "This person does not buy the headphones this week.",
                "not_for": "This person wants the headphones but waits for a different price.",
                "examples": [
                    "This person leaves the website without ordering the headphones."
                ],
            },
        },
    ),
    YesNoQuestion(
        campaign=(
            "Sony is selling the WH-1000XM5 headphones on its website for $400. "
            "This week Sony offers 20% cashback on that purchase. "
            "The cashback is capped at $80. "
            "Because 20% of $400 is $80, the buyer receives the full $80. "
            "The buyer pays $400 at checkout, and the $80 is returned afterward. "
            "Shipping is free."
        ),
        instructions={
            "question": (
                "Will you buy the Sony WH-1000XM5 headphones this week, "
                "pay $400 at checkout, and take the $80 cashback?"
            ),
            "inspect": "`campaign`",
            "focus": "Answer yes only if you pay $400 now and take the $80 cashback.",
        },
        criteria={
            "true": {
                "what": "This person buys the headphones now, pays $400, and takes the $80 cashback.",
                "not_for": "This person likes Sony, or plans to buy the headphones later, but does not buy them this week.",
                "examples": [
                    "This person orders the headphones, pays $400, and receives $80 back."
                ],
            },
            "false": {
                "what": "This person does not buy the headphones this week.",
                "not_for": "This person wants the headphones but will not pay $400 up front for cashback later.",
                "examples": [
                    "This person leaves the website without ordering the headphones."
                ],
            },
        },
    ),
    YesNoQuestion(
        campaign=(
            "The American Red Cross has mailed you a postcard. "
            "The postcard says a blood drive will be held this Sunday "
            "at a community center a short drive from your home. "
            "Giving blood takes about an hour."
        ),
        instructions={
            "question": "Will you sign up to give blood at that drive this Sunday?",
            "inspect": "`campaign`",
            "focus": "Answer yes only if you sign up to attend the drive this Sunday.",
        },
        criteria={
            "true": {
                "what": "This person signs up and gives blood at the drive this Sunday.",
                "not_for": "This person approves of blood donation but does not go on Sunday.",
                "examples": [
                    "This person spends about an hour at the drive this Sunday."
                ],
            },
            "false": {
                "what": "This person does not sign up for the drive.",
                "not_for": "This person is glad that other people give blood.",
                "examples": ["This person sets the postcard aside and does not go."],
            },
        },
    ),
)
