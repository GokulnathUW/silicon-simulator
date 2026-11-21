"""A few 'which is better' scenarios for a pipeline check."""

from dataclasses import dataclass
from typing import Literal, TypedDict


class ChoiceInstructions(TypedDict):
    """The question, the state field it reads, and what the choice is about."""

    question: str
    inspect: str
    focus: str


class ChoiceCriterion(TypedDict):
    """What one option covers, what it does not, and an example."""

    what: str
    not_for: str
    examples: list[str]


@dataclass(frozen=True)
class ChoiceQuestion:
    """One campaign and the choice question about it."""

    campaign: str
    instructions: ChoiceInstructions
    choices: dict[str, ChoiceCriterion]
    category: Literal["choice"] = "choice"


CHOICE_QUESTIONS: tuple[ChoiceQuestion, ...] = (
    ChoiceQuestion(
        campaign=(
            "You are shopping for a laptop you will use for work and at home. "
            "You are ready to buy one this week. "
            "Shipping is free on the laptop you choose."
        ),
        instructions={
            "question": "Which laptop will you buy?",
            "inspect": "`campaign`",
            "focus": "Choose the one laptop that best meets your preferences.",
        },
        choices={
            "Dell XPS": {
                "what": (
                    "The Dell XPS costs $1,200. "
                    "It weighs 2.6 pounds, so it is easy to carry, "
                    "and the warranty lasts one year."
                ),
                "not_for": "Low budget or longer warranty.",
                "examples": ["You choose the Dell XPS because it is lighter"],
            },
            "Lenovo ThinkPad": {
                "what": (
                    "The Lenovo ThinkPad costs $900. "
                    "It weighs 4.2 pounds, so it is heavier to carry, "
                    "and the warranty lasts three years."
                ),
                "not_for": "Lightweight laptop.",
                "examples": [
                    "You choose the Lenovo ThinkPad because it is cheaper and has a longer warranty."
                ],
            },
        },
    ),
    ChoiceQuestion(
        campaign=(
            "You need dinner on three weeknights this week. "
            "You have not bought the food yet."
        ),
        instructions={
            "question": "Which option will you use for those three dinners?",
            "inspect": "`campaign`",
            "focus": "Choose the one way that is the most convenient.",
        },
        choices={
            "HelloFresh": {
                "what": (
                    "HelloFresh delivers the ingredients for $70. "
                    "You skip the grocery shop and most of the prep, "
                    "so the evening takes less time."
                ),
                "not_for": "If you prefer to save money.",
                "examples": ["You choose HelloFresh because it is more convenient."],
            },
            "Groceries": {
                "what": (
                    "The same three meals cost about $45 in groceries. "
                    "That is less money, but you spend the time shopping and cooking."
                ),
                "not_for": "If you prefer to save time or don't cook.",
                "examples": [
                    "You choose groceries because you prefer to cook at home.",
                    "You choose groceries because you prefer to save time.",
                ],
            },
        },
    ),
    ChoiceQuestion(
        campaign=(
            "You need dinner on three weeknights this week. "
            "You have not bought the food yet."
        ),
        instructions={
            "question": "Which option will you use for those three dinners?",
            "inspect": "`campaign`",
            "focus": "Choose the one way you will get those three dinners.",
        },
        choices={
            "HelloFresh": {
                "what": "HelloFresh delivers the ingredients for $70.",
                "not_for": "Cook at home.",
                "examples": ["You choose HelloFresh."],
            },
            "Groceries": {
                "what": "The same three meals cost about $45 in groceries.",
                "not_for": "Ordering the HelloFresh delivery.",
                "examples": ["This person buys the groceries."],
            },
        },
    ),
    ChoiceQuestion(
        campaign=(
            "The city council will spend a budget increase on one change this year. "
            "The increase is large enough for one change and no more."
        ),
        instructions={
            "question": "Which change will you support?",
            "inspect": "`campaign`",
            "focus": "Choose the one change you will support.",
        },
        choices={
            "Firefighter wages": {
                "what": (
                    "The council raises city firefighters' wages. "
                    "Firefighters earn more. "
                    "The city adds no new station and no new truck, "
                    "so residents keep the same fire service they have now."
                ),
                "not_for": "A tax rebate, downtown police overtime, or payments to landlords.",
                "examples": ["You give the budget increase to firefighter wages."],
            },
            "Warehouse tax rebate": {
                "what": (
                    "The council gives a five-year tax rebate "
                    "to one company that opens a warehouse. "
                    "That company pays less tax. "
                    "Businesses already in the city do not get the rebate, "
                    "and the city gives up that tax for five years."
                ),
                "not_for": "Firefighter wages, downtown police overtime, or payments to landlords.",
                "examples": ["You give the budget increase to that company's tax rebate."],
            },
            "Downtown police overtime": {
                "what": (
                    "The council pays police overtime on Friday and Saturday nights "
                    "in the downtown bar district. "
                    "Officers earn more for those shifts, "
                    "and those streets have more officers at night. "
                    "Residential neighborhoods get no extra patrols."
                ),
                "not_for": "Firefighter wages, a warehouse tax rebate, or payments to landlords.",
                "examples": ["You give the budget increase to downtown weekend police overtime."],
            },
            "Landlord rent freeze payments": {
                "what": (
                    "The council pays landlords who agree not to raise rent for two years. "
                    "Tenants in those buildings keep the same rent, "
                    "and the payment goes to the landlords. "
                    "Tenants in buildings that do not join get no protection."
                ),
                "not_for": "Firefighter wages, a warehouse tax rebate, or downtown police overtime.",
                "examples": ["You give the budget increase to those landlords."],
            },
        },
    ),
)
