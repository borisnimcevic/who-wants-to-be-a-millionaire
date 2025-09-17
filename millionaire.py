#!/usr/bin/env python3
"""
Terminal "Millionaire"-style quiz game

Updates:
- Replaced **50:50** with **Take a Shot**: removes **one** wrong answer per use.
- You can use **Take a Shot** up to **7 times per game**.
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

    def swap_question(self) -> None:
        if not self.lifelines.swap:
            print(c("You already used Swap the Question.", Style.DIM))
            return
        remaining = list(range(self.current_index + 1, len(self.questions)))
        if not remaining:
            print(c("No remaining questions to swap with.", Style.DIM))
            return
        j = self.rng.choice(remaining)
        self.questions[self.current_index], self.questions[j] = self.questions[j], self.questions[self.current_index]
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
            valid = set(["A", "B", "C", "D", "W", "T", "U", "S"]
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
            if choice == "S":
                self.swap_question()
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
    # WATER
    Question(prompt="What percentage of Earth's water is freshwater?", choices={
             "A": "2.5%", "B": "10%", "C": "25%", "D": "50%"}, correct="A"),
    Question(prompt="Which process in the water cycle is responsible for cloud formation?", choices={
             "A": "Precipitation", "B": "Condensation", "C": "Infiltration", "D": "Transpiration"}, correct="B"),
    Question(prompt="Which ocean current is known as a 'conveyor belt' for global heat transfer?", choices={
             "A": "Gulf Stream", "B": "El Niño", "C": "Humboldt Current", "D": "Monsoon Drift"}, correct="A"),
    Question(prompt="What is desalination used for?", choices={
             "A": "Removing salt from seawater", "B": "Adding minerals to freshwater", "C": "Filtering groundwater", "D": "Converting vapor to liquid"}, correct="A"),
    Question(prompt="Which country has the largest renewable freshwater resources?", choices={
             "A": "Brazil", "B": "Canada", "C": "Russia", "D": "China"}, correct="A"),
    Question(prompt="Which property allows water to rise in thin tubes against gravity?", choices={
             "A": "Viscosity", "B": "Capillary action", "C": "Density anomaly", "D": "Hydrophobicity"}, correct="B"),
    Question(prompt="What is eutrophication primarily caused by?", choices={
             "A": "Excess nutrients", "B": "Oil spills", "C": "Thermal pollution", "D": "Acid rain"}, correct="A"),
    Question(prompt="Which of these is the largest body of freshwater by volume?", choices={
             "A": "Lake Victoria", "B": "Lake Superior", "C": "Lake Baikal", "D": "Caspian Sea"}, correct="C"),
    Question(prompt="Which process purifies water naturally as it passes through soil?", choices={
             "A": "Filtration", "B": "Evaporation", "C": "Desalination", "D": "Oxidation"}, correct="A"),
    Question(prompt="Which country built the 'Great Man-Made River' project to transport water?",
             choices={"A": "Egypt", "B": "Libya", "C": "Saudi Arabia", "D": "Iran"}, correct="B"),

    # MARKETING
    Question(prompt="Which metric indicates how many times an ad is shown?", choices={
             "A": "CTR", "B": "Impressions", "C": "Conversion Rate", "D": "Bounce Rate"}, correct="B"),
    Question(prompt="Which pricing strategy sets a low price to enter a competitive market?", choices={
             "A": "Skimming", "B": "Penetration", "C": "Premium", "D": "Value-based"}, correct="B"),
    Question(prompt="In SEO, what does SERP stand for?", choices={
             "A": "Search Engine Results Page", "B": "Search Engine Ranking Policy", "C": "Search Engine Reach Percentage", "D": "Search Engagement Rate Process"}, correct="A"),
    Question(prompt="Which psychological principle uses scarcity to increase demand?", choices={
             "A": "Reciprocity", "B": "Anchoring", "C": "Scarcity Effect", "D": "Priming"}, correct="C"),
    Question(prompt="What is the main goal of content marketing?", choices={
             "A": "Direct sales", "B": "Customer value and engagement", "C": "Paid advertising", "D": "SEO bypass"}, correct="B"),
    Question(prompt="Which social media platform is most associated with B2B marketing?", choices={
             "A": "Facebook", "B": "Instagram", "C": "LinkedIn", "D": "Snapchat"}, correct="C"),
    Question(prompt="Which color is often used in marketing to trigger urgency?", choices={
             "A": "Green", "B": "Blue", "C": "Red", "D": "Purple"}, correct="C"),
    Question(prompt="A marketing funnel typically starts with which stage?", choices={
             "A": "Awareness", "B": "Consideration", "C": "Decision", "D": "Retention"}, correct="A"),
    Question(prompt="Which KPI measures the cost of acquiring one new customer?",
             choices={"A": "CPC", "B": "CAC", "C": "CPA", "D": "CLV"}, correct="B"),
    Question(prompt="What does 'viral marketing' rely on?", choices={
             "A": "Paid ads", "B": "Word of mouth and sharing", "C": "Telemarketing", "D": "Cold emailing"}, correct="B"),

    # SALES
    Question(prompt="What does CRM stand for?", choices={
             "A": "Customer Revenue Management", "B": "Customer Relationship Management", "C": "Consumer Resource Mapping", "D": "Client Retention Model"}, correct="B"),
    Question(prompt="What is an 'upsell'?", choices={
             "A": "Offering a discount", "B": "Selling a higher-value product", "C": "Renewing a subscription", "D": "Customer complaint handling"}, correct="B"),
    Question(prompt="What is the 'sales pipeline'?", choices={
             "A": "Customer complaint queue", "B": "Stages of sales process", "C": "Logistics supply chain", "D": "Marketing campaign list"}, correct="B"),
    Question(prompt="What is a common closing technique in sales?", choices={
             "A": "The assumptive close", "B": "The passive close", "C": "The silent close", "D": "The evasive close"}, correct="A"),
    Question(prompt="In sales, what does 'churn rate' measure?", choices={
             "A": "Number of new customers", "B": "Rate of customer loss", "C": "Total revenue per client", "D": "Upsell success"}, correct="B"),
    Question(prompt="Which sales strategy focuses on solving customer problems?", choices={
             "A": "Transactional selling", "B": "Solution selling", "C": "Cold calling", "D": "Hard closing"}, correct="B"),
    Question(prompt="Which of these is a key benefit of consultative selling?", choices={
             "A": "Shorter sales cycles", "B": "Higher trust and loyalty", "C": "Cheaper marketing", "D": "Immediate conversions"}, correct="B"),
    Question(prompt="In sales forecasting, 'bottom-up' means starting with what?", choices={
             "A": "Industry averages", "B": "Customer segments and units sold", "C": "CEO projections", "D": "Historical profits"}, correct="B"),
    Question(prompt="Which stage comes last in the AIDA sales model?", choices={
             "A": "Awareness", "B": "Interest", "C": "Desire", "D": "Action"}, correct="D"),
    Question(prompt="What is 'cross-selling'?", choices={"A": "Selling to competitors",
             "B": "Selling complementary products", "C": "Selling to new industries", "D": "International selling"}, correct="B"),

    # ENTREPRENEURSHIP
    Question(prompt="What is a 'minimum viable product' (MVP)?", choices={
             "A": "A prototype with core features", "B": "The final polished product", "C": "A premium version of a product", "D": "An idea without execution"}, correct="A"),
    Question(prompt="Which document outlines a startup’s vision, mission, and strategy?", choices={
             "A": "Term sheet", "B": "Business plan", "C": "Pitch deck", "D": "Balance sheet"}, correct="B"),
    Question(prompt="Which type of funding involves giving up equity?", choices={
             "A": "Debt financing", "B": "Bootstrapping", "C": "Venture capital", "D": "Revenue-based financing"}, correct="C"),
    Question(prompt="Which entrepreneur co-founded Microsoft?", choices={
             "A": "Steve Jobs", "B": "Larry Page", "C": "Bill Gates", "D": "Elon Musk"}, correct="C"),
    Question(prompt="What is a common characteristic of successful entrepreneurs?", choices={
             "A": "Risk aversion", "B": "Resilience", "C": "Strict conformity", "D": "Avoiding innovation"}, correct="B"),
    Question(prompt="Which startup methodology emphasizes quick testing and iteration?", choices={
             "A": "Waterfall", "B": "Lean Startup", "C": "Agile Manufacturing", "D": "Six Sigma"}, correct="B"),
    Question(prompt="Which entrepreneur founded SpaceX?", choices={
             "A": "Richard Branson", "B": "Elon Musk", "C": "Jeff Bezos", "D": "Larry Ellison"}, correct="B"),
    Question(prompt="What is a 'unicorn' company?", choices={
             "A": "A business with magical branding", "B": "A startup valued at $1B+", "C": "A one-founder business", "D": "A non-profit with global reach"}, correct="B"),
    Question(prompt="Which entrepreneur started Amazon in a garage?", choices={
             "A": "Steve Jobs", "B": "Jeff Bezos", "C": "Jack Ma", "D": "Mark Zuckerberg"}, correct="B"),
    Question(prompt="What is 'bootstrapping' in entrepreneurship?", choices={
             "A": "Seeking early VC funding", "B": "Self-funding a business", "C": "Crowdfunding", "D": "Using government grants"}, correct="B"),

    # ELECTRONICS
    Question(prompt="Which component converts AC to DC?", choices={
             "A": "Resistor", "B": "Rectifier", "C": "Capacitor", "D": "Transformer"}, correct="B"),
    Question(prompt="What does LED stand for?", choices={
             "A": "Light Emitting Diode", "B": "Low Energy Device", "C": "Linear Electric Driver", "D": "Long Emission Display"}, correct="A"),
    Question(prompt="Which unit is used to measure electrical resistance?", choices={
             "A": "Ampere", "B": "Volt", "C": "Ohm", "D": "Watt"}, correct="C"),
    Question(prompt="Which law explains electromagnetic induction?", choices={
             "A": "Ohm's Law", "B": "Faraday's Law", "C": "Coulomb's Law", "D": "Newton's Law"}, correct="B"),
    Question(prompt="Which device stores charge and can release it quickly?", choices={
             "A": "Diode", "B": "Inductor", "C": "Capacitor", "D": "Resistor"}, correct="C"),
    Question(prompt="What does a transistor primarily do?", choices={
             "A": "Amplify or switch signals", "B": "Store data", "C": "Generate electricity", "D": "Measure resistance"}, correct="A"),
    Question(prompt="Which material is commonly used as a semiconductor?", choices={
             "A": "Copper", "B": "Iron", "C": "Silicon", "D": "Carbon"}, correct="C"),
    Question(prompt="Which unit measures electrical power?", choices={
             "A": "Joule", "B": "Watt", "C": "Volt", "D": "Tesla"}, correct="B"),
    Question(prompt="What is the main function of a fuse?", choices={
             "A": "Store energy", "B": "Amplify current", "C": "Protect circuits from overcurrent", "D": "Switch signals"}, correct="C"),
    Question(prompt="Which component opposes changes in current flow?", choices={
             "A": "Capacitor", "B": "Inductor", "C": "Diode", "D": "Resistor"}, correct="B"),

    # PROGRAMMING
    Question(prompt="Which programming paradigm is based on objects and classes?", choices={
             "A": "Functional", "B": "Imperative", "C": "Object-Oriented", "D": "Procedural"}, correct="C"),
    Question(prompt="Which language is primarily used for web front-end development?",
             choices={"A": "Python", "B": "JavaScript", "C": "C++", "D": "Java"}, correct="B"),
    Question(prompt="What does 'API' stand for?", choices={
             "A": "Application Programming Interface", "B": "Automated Program Instruction", "C": "Advanced Protocol Integration", "D": "Application Process Interpreter"}, correct="A"),
    Question(prompt="Which sorting algorithm has average time complexity O(n log n)?", choices={
             "A": "Bubble Sort", "B": "Quick Sort", "C": "Insertion Sort", "D": "Selection Sort"}, correct="B"),
    Question(prompt="Which symbol is commonly used for comments in Python?", choices={
             "A": "//", "B": "#", "C": "/* */", "D": "--"}, correct="B"),
    Question(prompt="Which data structure uses FIFO order?", choices={
             "A": "Stack", "B": "Queue", "C": "Tree", "D": "Graph"}, correct="B"),
    Question(prompt="Which keyword is used to define a function in Python?", choices={
             "A": "func", "B": "def", "C": "function", "D": "fn"}, correct="B"),
    Question(prompt="Which type of error occurs at runtime?", choices={
             "A": "Syntax Error", "B": "Logical Error", "C": "Runtime Error", "D": "Compilation Error"}, correct="C"),
    Question(prompt="Which operator is used for string concatenation in Python?",
             choices={"A": "+", "B": "&", "C": ".", "D": "++"}, correct="A"),
    Question(prompt="Which keyword is used to create a class in Python?", choices={
             "A": "object", "B": "new", "C": "class", "D": "struct"}, correct="C"),

    # MANUFACTURING
    Question(prompt="Which process involves pouring molten metal into molds?", choices={
             "A": "Forging", "B": "Casting", "C": "Extrusion", "D": "Machining"}, correct="B"),
    Question(prompt="Which method is used to join metals using heat and filler material?", choices={
             "A": "Casting", "B": "Welding", "C": "Machining", "D": "Forging"}, correct="B"),
    Question(prompt="Which term describes the ability of a material to resist deformation?", choices={
             "A": "Ductility", "B": "Toughness", "C": "Strength", "D": "Elasticity"}, correct="C"),
    Question(prompt="Which process involves compressing powder into solid parts?", choices={
             "A": "Powder metallurgy", "B": "Injection molding", "C": "Casting", "D": "Extrusion"}, correct="A"),
    Question(prompt="Which manufacturing technique builds objects layer by layer?", choices={
             "A": "CNC machining", "B": "3D printing", "C": "Milling", "D": "Casting"}, correct="B"),
    Question(prompt="Which material property describes the ability to be stretched into wire?", choices={
             "A": "Malleability", "B": "Ductility", "C": "Hardness", "D": "Elasticity"}, correct="B"),
    Question(prompt="Which manufacturing system focuses on producing small batches efficiently?", choices={
             "A": "Mass production", "B": "Job shop", "C": "Continuous flow", "D": "Batch production"}, correct="D"),
    Question(prompt="Which quality tool uses a cause-and-effect diagram?", choices={
             "A": "Histogram", "B": "Pareto chart", "C": "Ishikawa diagram", "D": "Scatter plot"}, correct="C"),
    Question(prompt="Which process improves material hardness through heat treatment?", choices={
             "A": "Tempering", "B": "Annealing", "C": "Quenching", "D": "Forging"}, correct="C"),
    Question(prompt="Which manufacturing philosophy focuses on eliminating defects?", choices={
             "A": "Lean", "B": "Six Sigma", "C": "Kaizen", "D": "Scrum"}, correct="B"),
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

