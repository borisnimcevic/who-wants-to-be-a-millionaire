#!/usr/bin/env python3
"""
Terminal "Millionaire"-style quiz game

Updates:
- Replaced **50:50** with **Take a Shot**: removes **one** wrong answer per use.
- You can use **Take a Shot** up to **7 times per game**.
- Keys: [T] Take a Shot, [U] Audience, [P] Phone a Friend, [W] Walk away, A/B/C/D to answer.
- Robust input handling: gracefully exits on non-interactive stdin (EOFError/OSError).
- Removed choices now disappear completely from the screen instead of just being dimmed.
"""
from __future__ import annotations

import json
import os
import random
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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

    @staticmethod
    def from_dict(d: dict) -> "Question":
        choices = d.get("choices") or {}
        normalized = {k.upper(): v for k, v in choices.items()}
        if not normalized and isinstance(d.get("choices"), list):
            letters = list("ABCD")
            normalized = {letters[i]: v for i,
                          v in enumerate(d["choices"]) if i < 4}
        answer = d.get("answer", "").upper()
        if answer not in normalized:
            raise ValueError("Invalid or missing 'answer' matching choices")
        if len(normalized) != 4 or set(normalized.keys()) != set("ABCD"):
            raise ValueError("'choices' must provide A, B, C, D")
        return Question(prompt=d["question"], choices=normalized, correct=answer, hint=d.get("hint"))


DEFAULT_LADDER = [
    100, 200, 300, 500, 1000,
    2000, 4000, 8000, 16000, 32000,
    64000, 125000, 250000, 500000, 1000000,
]

CHECKPOINTS = {4, 9}


@dataclass
class Lifelines:
    take_shot_uses: int = 7
    audience: bool = True
    phone: bool = True

    def any_left(self) -> bool:
        return self.take_shot_uses > 0 or self.audience or self.phone


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
        candidates = [k for k in "ABCD" if k !=
                      correct and k not in self.eliminated]
        if not candidates:
            print(c("No wrong answers left to remove.", Style.DIM))
            return
        to_remove = self.rng.choice(candidates)
        self.eliminated.add(to_remove)
        self.lifelines.take_shot_uses -= 1
        print(c("Take a Shot removes:", Style.CYAN), to_remove, c(
            f"(remaining {self.lifelines.take_shot_uses})", Style.DIM))

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

    def phone_friend(self) -> None:
        if not self.lifelines.phone:
            print(c("You already phoned a friend.", Style.DIM))
            return
        correct = self.questions[self.current_index].correct
        options = [k for k in "ABCD" if k not in self.eliminated]
        if self.rng.random() < 0.75:
            guess = correct
        else:
            wrong = [k for k in options if k != correct]
            guess = self.rng.choice(wrong) if wrong else correct
        print(c("Your friend thinks the answer is:",
              Style.CYAN), c(guess, Style.BOLD))
        if self.questions[self.current_index].hint:
            print(c("Friend adds:", Style.CYAN),
                  self.questions[self.current_index].hint)
        self.lifelines.phone = False

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
        print(c("\nWho Wants To Be A (Terminal) Millionaire",
              Style.BOLD, Style.MAGENTA))
        print("Question", self.current_index + 1, "/", len(self.ladder))
        print("Prize:", c(f"${self.current_prize():,}", Style.YELLOW))
        if self.lifelines.any_left():
            ll = []
            if self.lifelines.take_shot_uses > 0:
                ll.append(
                    f"[T] Take a Shot (x{self.lifelines.take_shot_uses})")
            if self.lifelines.audience:
                ll.append("[U] Audience")
            if self.lifelines.phone:
                ll.append("[P] Phone a Friend")
            print(c("Lifelines:", Style.DIM), ", ".join(ll))
        print(c("Type A/B/C/D to answer, W to walk away, or lifeline keys.", Style.DIM))
        print()

    def render_question(self) -> None:
        q = self.questions[self.current_index]
        print(c(q.prompt, Style.BOLD))
        for k in "ABCD":
            if k in self.eliminated:
                continue  # don't show eliminated options
            print(f"  {k}. {q.choices[k]}")
        print()

    def get_input(self) -> str:
        while True:
            try:
                ans = input(c("Your choice: ", Style.BOLD)).strip().upper()
            except (EOFError, OSError):
                print(c("Input error or stream closed. Exiting game.", Style.RED))
                raise SystemExit(1)
            valid = set(["A", "B", "C", "D", "W", "T", "U", "P"]
                        ) - self.eliminated
            if ans in valid:
                return ans
            print(c("Invalid input. Try again.", Style.RED))

    # ---------- Flow ----------
    def play(self) -> None:
        while self.current_index < len(self.ladder):
            self.clear_screen()
            self.render_header()
            self.render_question()

            choice = self.get_input()
            if choice == "W":
                print(c("You chose to walk away with:", Style.CYAN),
                      c(f"${self.money():,}", Style.YELLOW))
                return
            if choice == "T":
                self.take_a_shot()
                continue
            if choice == "U":
                self.ask_audience()
                continue
            if choice == "P":
                self.phone_friend()
                continue

            correct = self.questions[self.current_index].correct
            if choice == correct:
                print(c("Correct!", Style.GREEN), c(
                    f"You win ${self.current_prize():,}", Style.YELLOW))
                self.current_index += 1
                if self.current_index == len(self.ladder):
                    print(
                        c("Congratulations! You are a (terminal) millionaire!", Style.MAGENTA, Style.BOLD))
                    return
                try:
                    input(c("Press Enter for the next question...", Style.DIM))
                except (EOFError, OSError):
                    print()
            else:
                print(c("Sorry, that's incorrect.", Style.RED))
                guaranteed = self.checkpoint_money()
                if guaranteed:
                    print(c("You leave with:", Style.CYAN),
                          c(f"${guaranteed:,}", Style.YELLOW))
                else:
                    print(c("You leave with $0.", Style.YELLOW))
                print(c(f"The correct answer was {correct}.", Style.DIM))
                return


# ---------------------- Sample Questions ----------------------
SAMPLE_QUESTIONS: List[Question] = [
    Question(prompt="Which of these animals is known for building dams?", choices={
             "A": "Beaver", "B": "Otter", "C": "Seal", "D": "Walrus"}, correct="A", hint="Flat tail, big teeth."),
    Question(prompt="In Python, what does the 'len' function return?", choices={
             "A": "The last element", "B": "The length/size", "C": "The first index", "D": "The memory address"}, correct="B", hint="Think: how many?"),
    Question(prompt="Which planet is known as the Red Planet?", choices={
             "A": "Venus", "B": "Jupiter", "C": "Mars", "D": "Saturn"}, correct="C"),
    Question(prompt="What does 'HTTP' stand for?", choices={
             "A": "HyperText Transfer Protocol", "B": "High Transfer Text Protocol", "C": "Hyperlink Transmission Process", "D": "Host Transfer Type Protocol"}, correct="A"),
    Question(prompt="Which language is primarily used for styling web pages?", choices={
             "A": "HTML", "B": "CSS", "C": "SQL", "D": "C++"}, correct="B"),
    Question(prompt="Which data structure uses FIFO order?", choices={
             "A": "Stack", "B": "Queue", "C": "Tree", "D": "Graph"}, correct="B"),
    Question(prompt="Which ocean is the largest?", choices={
             "A": "Atlantic", "B": "Indian", "C": "Pacific", "D": "Arctic"}, correct="C"),
    Question(prompt="Which device converts AC to DC?", choices={
             "A": "Transformer", "B": "Rectifier", "C": "Inverter", "D": "Regulator"}, correct="B"),
    Question(prompt="What is the capital of Sweden?", choices={
             "A": "Gothenburg", "B": "Stockholm", "C": "Malmö", "D": "Uppsala"}, correct="B"),
    Question(prompt="Which sorting algorithm has average complexity O(n log n)?", choices={
             "A": "Bubble Sort", "B": "Insertion Sort", "C": "Merge Sort", "D": "Selection Sort"}, correct="C"),
    Question(prompt="What is the chemical symbol for Gold?", choices={
             "A": "Gd", "B": "Go", "C": "Au", "D": "Ag"}, correct="C"),
    Question(prompt="Which port does HTTPS typically use?", choices={
             "A": "80", "B": "21", "C": "22", "D": "443"}, correct="D"),
    Question(prompt="Which mathematician introduced the set of axioms for Euclidean geometry?", choices={
             "A": "Pythagoras", "B": "Euclid", "C": "Archimedes", "D": "Newton"}, correct="B"),
    Question(prompt="What does RAM stand for?", choices={
             "A": "Random Access Memory", "B": "Readily Available Module", "C": "Rapid Access Module", "D": "Read-Allocate Memory"}, correct="A"),
    Question(prompt="Which company created the Linux kernel?", choices={
             "A": "Red Hat", "B": "IBM", "C": "Linus Torvalds", "D": "Canonical"}, correct="C", hint="Not a company 😉"),
]


# ---------------------- Loading ----------------------
def load_questions_from_file(path: str) -> List[Question]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Top-level JSON must be a list of questions")
    return [Question.from_dict(x) for x in data]


# ---------------------- Main ----------------------
def main(argv: List[str]) -> int:
    rng = random.Random()
    rng.seed()
    if len(argv) > 2:
        print("Usage: python millionaire.py [questions.json]")
        return 2
    if len(argv) == 2:
        try:
            questions = load_questions_from_file(argv[1])
        except Exception as e:
            print(c("Failed to load questions:", Style.RED), e)
            return 1
    else:
        questions = SAMPLE_QUESTIONS

    if len(questions) < len(DEFAULT_LADDER):
        print(c(f"Need at least {len(DEFAULT_LADDER)
                                 } questions (got {len(questions)}).", Style.RED))
        print(c("Tip: reduce DEFAULT_LADDER length or add more questions.", Style.DIM))
        return 1

    rng.shuffle(questions)
    questions = questions[: len(DEFAULT_LADDER)]

    game = Game(questions=questions, rng=rng)
    game.play()
    print(c("Thanks for playing!", Style.DIM))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

