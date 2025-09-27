#!/usr/bin/env python3
"""
Terminal "Millionaire"-style quiz game

Updates:
- Replaced **50:50** with **Take a Shot**: removes **one** wrong answer per use.
- You can use **Take a Shot** up to **6 times per game**.
- Replaced **Phone a Friend** with **Swap the Question**: once per game, swap the current question for another random one.
- Keys: [T] Take a Shot, [U] Audience, [S] Swap the Question, [W] Walk away, A/B/C/D to answer.
- Robust input handling: gracefully exits on non-interactive stdin (EOFError/OSError).
- Removed choices now disappear completely from the screen instead of just being dimmed.
"""

from __future__ import annotations

import json
import os
import random
import sys
from os import listdir
from os.path import isfile, join
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import defaultdict
from itertools import cycle
from collections import defaultdict, deque

# ---------------------- Constants --------------------

USED_QUESTIONS_DIR_PATH = ".cache/used"


# ---------------------- Styling ----------------------


class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"


def c(text: str, *styles: str) -> str:
    return "".join(styles) + text + Style.RESET


# ---------------------- Data ----------------------
@dataclass
class Question:
    prompt: str
    choices: Dict[str, str]
    correct: str  # 'A'/'B'/'C'/'D'
    hint: Optional[str] = None
    category: str = "General"

    @staticmethod
    def from_dict(d) -> Question:
        choices = d.get("choices") or {}
        normalized = {k.upper(): v for k, v in choices.items()}
        if not normalized and isinstance(d.get("choices"), list):
            letters = list("ABCD")
            normalized = {letters[i]: v for i, v in enumerate(d["choices"]) if i < 4}
        correct = d.get("correct", "").upper()
        if correct not in normalized:
            raise ValueError("Invalid or missing 'correct' matching choices")
        if len(normalized) != 4 or set(normalized.keys()) != set("ABCD"):
            raise ValueError("'choices' must provide A, B, C, D")
        print(d)
        return Question(
            prompt=d["prompt"],
            choices=normalized,
            correct=correct,
            hint=d.get("hint"),
            category=d.get("category", "General"),
        )

    def to_dict(self):
        return {
            "prompt": self.prompt,
            "choices": self.choices,
            "correct": self.correct,
            "hint": self.hint,
            "category": self.category,
        }


DEFAULT_LADDER = [
    100,
    200,
    300,
    500,
    1000,
    2000,
    4000,
    8000,
    16000,
    32000,
    64000,
    125000,
    250000,
    500000,
    1000000,
]

CHECKPOINTS = {4, 9}


@dataclass
class Lifelines:
    take_shot_uses: int = 6
    audience: bool = True
    swap: bool = True

    def any_left(self) -> bool:
        return self.take_shot_uses > 0 or self.audience or self.swap


# ---------------------- Game Engine ----------------------
@dataclass
class Game:
    questions: List[Question]
    ladder: List[int] = field(default_factory=lambda: DEFAULT_LADDER.copy())
    lifelines: Lifelines = field(default_factory=Lifelines)
    rng: random.Random = field(default_factory=random.Random)

    current_index: int = 0
    eliminated: set[str] = field(default_factory=set)

    def money(self) -> int:
        return self.ladder[self.current_index - 1] if self.current_index > 0 else 0

    def checkpoint_money(self) -> int:
        last = 0
        for i in CHECKPOINTS:
            if self.current_index - 1 >= i:
                last = self.ladder[i]
        return last

    def current_prize(self) -> int:
        return self.ladder[self.current_index]

    # ---------- Lifelines ----------
    def take_a_shot(self) -> None:
        if self.lifelines.take_shot_uses <= 0:
            print(c("No Take a Shot uses left.", Style.DIM))
            return
        correct = self.questions[self.current_index].correct
        candidates = [k for k in "ABCD" if k != correct and k not in self.eliminated]
        if not candidates:
            print(c("No wrong answers left to remove.", Style.DIM))
            return
        to_remove = self.rng.choice(candidates)
        self.eliminated.add(to_remove)
        self.lifelines.take_shot_uses -= 1
        print(
            c("Take a Shot removes:", Style.CYAN),
            to_remove,
            c(f"(remaining {self.lifelines.take_shot_uses})", Style.DIM),
        )

    def ask_audience(self) -> None:
        if not self.lifelines.audience:
            print(c("You already asked the audience.", Style.DIM))
            return
        correct = self.questions[self.current_index].correct
        base = {k: 1.0 for k in "ABCD" if k not in self.eliminated}
        base[correct] = 3.0
        total = sum(base.values())
        weights = {k: v / total for k, v in base.items()}
        percentages = {}
        remaining = 100
        keys = list(weights.keys())
        for i, k in enumerate(keys):
            if i == len(keys) - 1:
                percentages[k] = remaining
            else:
                expected = weights[k] * 100
                val = int(max(0, round(self.rng.gauss(expected, 6))))
                val = min(val, remaining)
                percentages[k] = val
                remaining -= val
        print(c("Audience poll:", Style.CYAN))
        for k in "ABCD":
            if k in percentages:
                print(f"  {k}: {percentages[k]}%")
        self.lifelines.audience = False

    def swap_question(self) -> None:
        if not self.lifelines.swap:
            print(c("You already used Swap the Question.", Style.DIM))
            return
        remaining = list(range(self.current_index + 1, len(self.questions)))
        if not remaining:
            print(c("No remaining questions to swap with.", Style.DIM))
            return
        j = self.rng.choice(remaining)
        self.questions[self.current_index], self.questions[j] = (
            self.questions[j],
            self.questions[self.current_index],
        )
        self.eliminated.clear()
        self.lifelines.swap = False
        print(c("Swapped! You've got a new question.", Style.CYAN))

    # ---------- I/O ----------
    def clear_screen(self) -> None:
        try:
            if os.name == "nt":
                os.system("cls")
            else:
                os.system("clear")
        except Exception:
            pass

    def render_header(self) -> None:
        print(
            c("\nWho Wants To Be A (Terminal) Millionaire", Style.BOLD, Style.MAGENTA)
        )
        print("Question", self.current_index + 1, "/", len(self.ladder))
        print("Prize:", c(f"Schmeckles {self.current_prize():,}", Style.YELLOW))
        if self.lifelines.any_left():
            ll = []
            if self.lifelines.take_shot_uses > 0:
                ll.append(f"[T] Take a Shot (x{self.lifelines.take_shot_uses})")
            if self.lifelines.audience:
                ll.append("[U] Audience")
            if self.lifelines.swap:
                ll.append("[S] Swap the Question")
            print(c("Lifelines:", Style.DIM), ", ".join(ll))
        print(c("Type A/B/C/D to answer, W to walk away, or lifeline keys.", Style.DIM))
        print()

    def render_question(self) -> None:
        q = self.questions[self.current_index]
        print(c(q.prompt, Style.BOLD))
        for k in "ABCD":
            if k in self.eliminated:
                continue
            print(f"  {k}. {q.choices[k]}")
        print()

    def get_input(self) -> str:
        while True:
            try:
                ans = input(c("Your choice: ", Style.BOLD)).strip().upper()
            except (EOFError, OSError):
                print(c("Input error or stream closed. Exiting game.", Style.RED))
                raise SystemExit(1)
            valid = set(["A", "B", "C", "D", "W", "T", "U", "S"]) - self.eliminated
            if ans in valid:
                return ans
            print(c("Invalid input. Try again.", Style.RED))

    # ---------- Flow ----------
    def play(self) -> None:
        while self.current_index < len(self.ladder):
            self.clear_screen()
            self.render_header()
            self.render_question()
            used_questions = load_questions_from_dir(USED_QUESTIONS_DIR_PATH)
            with open(
                join(USED_QUESTIONS_DIR_PATH, "questions.json"), "w+"
            ) as used_questions_file:
                used_questions.append(self.questions[self.current_index])
                _ = used_questions_file.write(
                    json.dumps([x.to_dict() for x in used_questions])
                )

            choice = self.get_input()
            if choice == "W":
                print(
                    c("You chose to walk away with:", Style.CYAN),
                    c(f"${self.money():,}", Style.YELLOW),
                )
                return
            if choice == "T":
                self.take_a_shot()
                continue
            if choice == "U":
                self.ask_audience()
                continue
            if choice == "S":
                self.swap_question()
                continue

            correct = self.questions[self.current_index].correct
            if choice == correct:
                print(
                    c("Correct!", Style.GREEN),
                    c(f"You win ${self.current_prize():,}", Style.YELLOW),
                )
                self.current_index += 1
                self.eliminated.clear()
                if self.current_index == len(self.ladder):
                    print(
                        c(
                            "Congratulations! You are a (terminal) millionaire!",
                            Style.MAGENTA,
                            Style.BOLD,
                        )
                    )
                    return
                try:
                    input(c("Press Enter for the next question...", Style.DIM))
                except (EOFError, OSError):
                    print()
            else:
                print(c("Sorry, that's incorrect.", Style.RED))
                guaranteed = self.checkpoint_money()
                if guaranteed:
                    print(
                        c("You leave with:", Style.CYAN),
                        c(f"${guaranteed:,}", Style.YELLOW),
                    )
                else:
                    print(c("You leave with $0.", Style.YELLOW))
                print(c(f"The correct answer was {correct}.", Style.DIM))
                return


# ---------------------- Loading ----------------------
def load_questions_from_dir(path: str) -> List[Question]:
    onlyfiles = [f for f in listdir(path) if isfile(join(path, f))]
    questions: list[Question] = []
    for filename in onlyfiles:
        questions.extend(load_questions_from_file(join(path, filename)))

    return questions


def load_questions_from_file(path: str) -> List[Question]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Top-level JSON must be a list of questions")
    return [Question.from_dict(x) for x in data]


def balanced_sample_by_category(
    questions: List[Question], k: int, rng: random.Random
) -> List[Question]:
    """
    Return k questions sampled as evenly as possible across categories.
    Rotates through categories, starting at a random category each run.
    If a category runs out, it drops from the rotation.
    """
    # Group by category
    by_cat: Dict[str, List[Question]] = defaultdict(list)
    for q in questions:
        by_cat[q.category].append(q)

    # Shuffle questions within each category for randomness
    cats = list(by_cat.keys())
    for cat in cats:
        rng.shuffle(by_cat[cat])

    # Build a rotating deque of categories and randomize the starting point
    rng.shuffle(cats)  # randomize order first
    dq = deque(cats)
    if dq:
        offset = rng.randrange(len(dq))  # random starting category
        dq.rotate(-offset)

    result: List[Question] = []
    while dq and len(result) < k:
        cat = dq[0]  # look at current category
        if by_cat[cat]:
            # Take one from this category, then rotate to the next
            result.append(by_cat[cat].pop())
            dq.rotate(-1)
        else:
            # This category is exhausted; remove it from rotation
            dq.popleft()

    return result


# ---------------------- Main ----------------------
def main(argv: List[str]) -> int:
    rng = random.Random()
    rng.seed()
    if len(argv) > 2:
        print("Usage: python millionaire.py [questions_dir_path]")
        print(
            "`questions_dir_path` should contain json files (suggestion 1 file per category)"
        )
        return 2
    if len(argv) == 2:
        try:
            questions = load_questions_from_dir(argv[1])
        except Exception as e:
            print(c("Failed to load questions:", Style.RED), e)
            return 1
    else:
        questions = load_questions_from_dir("questions")

    if not os.path.exists(USED_QUESTIONS_DIR_PATH):
        os.makedirs(USED_QUESTIONS_DIR_PATH)
    used_questions = {
        x.prompt: x for x in load_questions_from_dir(USED_QUESTIONS_DIR_PATH)
    }
    questions = [x for x in questions if used_questions.get(x.prompt) is None]

    if len(questions) < len(DEFAULT_LADDER):
        print(
            c(
                f"Need at least {len(DEFAULT_LADDER)} questions (got {len(questions)}).",
                Style.RED,
            )
        )
        print(
            c(
                f"""Tip: reduce DEFAULT_LADDER length or add more questions,
                or clear the `{USED_QUESTIONS_DIR_PATH}` directory to reuse questions you already played.""",
                Style.DIM,
            )
        )
        return 1

    # rng.shuffle(questions)
    # questions = questions[: len(DEFAULT_LADDER)]

    total_needed = len(DEFAULT_LADDER)
    if len(questions) < total_needed:
        print(
            c(
                f"Need at least {total_needed} questions (got {len(questions)}).",
                Style.RED,
            )
        )
        print(c("Tip: reduce DEFAULT_LADDER length or add more questions.", Style.DIM))
        return 1

    questions = balanced_sample_by_category(questions, total_needed, rng)

    game = Game(questions=questions, rng=rng)
    game.play()
    print(c("Thanks for playing!", Style.DIM))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
