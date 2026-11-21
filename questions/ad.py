"""Ads and the scores to give them."""

from dataclasses import dataclass
from typing import TypedDict


class ScoreInstructions(TypedDict):
    """The question, the state field it reads, and what the score is about."""

    question: str
    inspect: str
    focus: str


class ScoreLevel(TypedDict):
    """What one point on the scale means, and the signs of it."""

    what: str
    signals: list[str]


@dataclass(frozen=True)
class Reaction:
    """One score asked of every advertisement."""

    name: str
    instructions: ScoreInstructions
    criteria: tuple[ScoreLevel, ...]


# I PROMISE the ads are all AI generated
ADS: tuple[str, ...] = (
    """\
FADE IN on a woman in a bathroom, in a bra, pinching her stomach in the mirror.
She turns sideways. The camera stays on the pinch.
WOMAN: I was going to wear the dress. Then I saw this.
She drops the dress on the floor.
CUT to a shake. She drinks it in the same mirror. Her stomach looks flat. The dress zips.
SUPER: SKINNY CO. Skip breakfast. Skip dinner. Drink this.
WOMAN, to the camera: They'll look. You'll let them.
END CARD: Skinny Co. The body you meant to have.""",
    """\
A rooftop at night. A man watches a woman bend over the cooler.
His friend elbows him.
FRIEND: Go.
MAN: Not until she stands up.
She stands, sees the black can in his hand, and walks over.
SUPER: NIGHTHOWLER. She knows what you came for.
He cracks the can. Foam runs down his hand. She takes it and drinks.
MAN: Told you.
END CARD: NightHowler. Get what you came for.""",
    """\
OPEN on a kitchen at 7am. A father and his kid are looking at a chair that leans.
KID: It wobbles.
FATHER: Then we fix it.
CUT to a hardware aisle. The kid picks a box of screws. It's the wrong one.
They put it back, take the right box, and the kid carries it to the counter.
CUT to the kitchen. The chair sits flat. The kid sits in it, carefully, then grins.
FATHER: Saturday's free if you want to do the gate.
END CARD: HARPER HARDWARE. Open at 7. Bring whoever's helping.""",
    """\
A woman on a crowded bus at the end of the day. She puts on headphones.
The bus noise falls away. A voice note from her sister plays.
SISTER: The cake collapsed. Come anyway.
The woman smiles, types "on my way," and stays on the bus past her stop.
She gets off at her sister's corner, still wearing the headphones, and takes them off at the door.
END CARD: LARK. Headphones that let the right things through.""",
)


REACTIONS: tuple[Reaction, ...] = (
    Reaction(
        name="distasteful",
        instructions={
            "question": "How distasteful do you find this advertisement?",
            "inspect": "`campaign`",
            "focus": (
                "Score poor taste. "
                "Crude or vulgar content raises this score "
                "even when the advertisement insults nobody."
            ),
        },
        criteria=(
            {
                "what": "You do not find this advertisement distasteful.",
                "signals": [
                    "The advertisement presents its product in an ordinary way.",
                    "Nothing in the advertisement is crude or vulgar.",
                ],
            },
            {
                "what": "You find this advertisement a little unpleasant.",
                "signals": [
                    "One moment is slightly crude.",
                    "The rest of the advertisement is ordinary.",
                ],
            },
            {
                "what": "You find this advertisement in poor taste.",
                "signals": [
                    "The advertisement uses a crude image or a crude line to get attention.",
                    "The crudeness is noticeable, and the advertisement is still easy to watch.",
                ],
            },
            {
                "what": "You find this advertisement clearly distasteful.",
                "signals": [
                    "The advertisement is built around something vulgar.",
                    "You would rather not keep watching it.",
                ],
            },
            {
                "what": "You find this advertisement deeply distasteful.",
                "signals": [
                    "The advertisement is vulgar from start to finish.",
                    "You would want it to stop.",
                ],
            },
        ),
    ),
    Reaction(
        name="offensive",
        instructions={
            "question": "How offensive do you find this advertisement?",
            "inspect": "`campaign`",
            "focus": (
                "Score insults aimed at a person or a group. "
                "Crude taste alone does not raise this score."
            ),
        },
        criteria=(
            {
                "what": "You do not find this advertisement offensive.",
                "signals": [
                    "The advertisement does not insult anyone.",
                    "The advertisement does not attack a person or a group.",
                ],
            },
            {
                "what": "You think a few people might bristle at this advertisement.",
                "signals": [
                    "One line is careless toward someone.",
                    "The sting of that line is mild.",
                ],
            },
            {
                "what": "You find this advertisement offensive to some people.",
                "signals": [
                    "A person or a group is the target of the advertisement.",
                    "The advertisement makes a joke at their expense.",
                ],
            },
            {
                "what": "You find this advertisement offensive.",
                "signals": [
                    "The advertisement demeans a person or a group.",
                    "That insult is what the advertisement uses to sell.",
                ],
            },
            {
                "what": "You find this advertisement deeply offensive.",
                "signals": [
                    "The advertisement deliberately degrades a person or a group.",
                    "The attack is the point of the advertisement.",
                ],
            },
        ),
    ),
    Reaction(
        name="stupid",
        instructions={
            "question": "How stupid do you find this advertisement?",
            "inspect": "`campaign`",
            "focus": (
                "Score how dumb the idea is. "
                "An unpleasant or insulting advertisement is not stupid for that reason."
            ),
        },
        criteria=(
            {
                "what": "You do not find this advertisement stupid.",
                "signals": [
                    "The idea of the advertisement makes sense.",
                    "You can take the pitch seriously.",
                ],
            },
            {
                "what": "You find this advertisement a bit dumb.",
                "signals": [
                    "One joke or one line is dumb.",
                    "The rest of the advertisement makes sense.",
                ],
            },
            {
                "what": "You find this advertisement dumb.",
                "signals": [
                    "The central idea is weak.",
                    "You can follow the pitch, and you do not take it very seriously.",
                ],
            },
            {
                "what": "You find this advertisement stupid.",
                "signals": [
                    "The idea is foolish.",
                    "You would dismiss the pitch.",
                ],
            },
            {
                "what": "You find this advertisement painfully stupid.",
                "signals": [
                    "The whole advertisement is a foolish idea.",
                    "Nothing in it is worth taking seriously.",
                ],
            },
        ),
    ),
    Reaction(
        name="attractive",
        instructions={
            "question": "How attractive do you find this advertisement?",
            "inspect": "`campaign`",
            "focus": "Score how attractive you find the advertisement.",
        },
        criteria=(
            {
                "what": "You do not find this advertisement attractive.",
                "signals": [
                    "There is nothing in the advertisement that you like.",
                    "You would look away from it.",
                ],
            },
            {
                "what": "You find this advertisement slightly attractive.",
                "signals": [
                    "One moment in the advertisement is pleasant.",
                    "The rest of the advertisement is forgettable.",
                ],
            },
            {
                "what": "You find this advertisement attractive.",
                "signals": [
                    "You would watch the advertisement through to the end.",
                    "You like the scene.",
                ],
            },
            {
                "what": "You find this advertisement very attractive.",
                "signals": [
                    "You like the people in the advertisement.",
                    "You would be glad to see the advertisement again.",
                ],
            },
            {
                "what": "You find this advertisement extremely attractive.",
                "signals": [
                    "Watching the advertisement is a pleasure.",
                    "You would show the advertisement to someone else.",
                ],
            },
        ),
    ),
    Reaction(
        name="influential",
        instructions={
            "question": "How likely is this advertisement to move you to act?",
            "inspect": "`campaign`",
            "focus": "Score how likely the advertisement is to move you to act.",
        },
        criteria=(
            {
                "what": "This advertisement would not move you to act.",
                "signals": [
                    "You feel no urge to do anything after watching it.",
                    "You forget the advertisement as soon as it ends.",
                ],
            },
            {
                "what": "This advertisement might stay in your mind for a moment.",
                "signals": [
                    "You notice the product.",
                    "You do not follow up on it.",
                ],
            },
            {
                "what": "This advertisement could move you to act.",
                "signals": [
                    "You would look the product up if doing so were easy.",
                    "You are not sure you would follow through.",
                ],
            },
            {
                "what": "This advertisement would move you to act.",
                "signals": [
                    "You would go to the product's website.",
                    "You would visit the store that sells it.",
                ],
            },
            {
                "what": "This advertisement would send you to get the product.",
                "signals": [
                    "You would buy the product or sign up for it.",
                    "You would do that soon.",
                ],
            },
        ),
    ),
)
