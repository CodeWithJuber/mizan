"""Build the Imtihan's faculty blocks (imtihan/quwa.py) as task files.

One block per faculty of Google DeepMind's cognitive framework that the older
blocks covered thinly: perception, generation, attention, memory, reasoning,
metacognition, executive functions, problem solving, social cognition. Every
item is written new for MIZAN (classic vignettes such as Sally-Anne are widely
published and so contaminated) and scored by rule. Expected answers are
computed here, not typed, and the long attention items are generated from a
fixed seed, so a rebuild gives the same files:

    python scripts/build_quwa_tasks.py            # writes backend/imtihan/tasks/<block>.jsonl
    python scripts/build_quwa_tasks.py --check    # fails if the files differ from a rebuild
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import deque
from pathlib import Path

TASKS = Path(__file__).resolve().parents[1] / "backend" / "imtihan" / "tasks"
SEED = 7890
CONFIDENCE = (
    "\nGive your answer, then on the last line write 'Confidence: N%' for how likely it is "
    "that your answer is right."
)
LETTER = "\nAnswer with the letter."


def choice(block: str, task_id: str, question: str, options: dict[str, str], expected: str) -> dict:
    lines = "\n".join(f"{letter}) {text}" for letter, text in options.items())
    return {
        "block": block,
        "id": task_id,
        "prompt": f"{question}\n{lines}{LETTER}",
        "score": {"kind": "choice", "expected": expected, "options": options},
    }


def item(block: str, task_id: str, prompt: str, score: dict, **extra) -> dict:
    return {"block": block, "id": task_id, **extra, "prompt": prompt, "score": score}


def number(value) -> dict:
    return {"kind": "number", "expected": str(value)}


def turns(*pairs: str) -> list[dict]:
    return [
        {"role": "user" if index % 2 == 0 else "assistant", "content": text}
        for index, text in enumerate(pairs)
    ]


# ── perception: reading symbols, counts, tables and pictures made of text ──


def _shapes(picture: list[str]) -> int:
    seen: set[tuple[int, int]] = set()
    count = 0
    for row, line in enumerate(picture):
        for column, char in enumerate(line):
            if char != "#" or (row, column) in seen:
                continue
            count += 1
            queue = deque([(row, column)])
            seen.add((row, column))
            while queue:
                r, c = queue.popleft()
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = r + dr, c + dc
                    if (
                        0 <= nr < len(picture)
                        and 0 <= nc < len(picture[nr])
                        and picture[nr][nc] == "#"
                        and (nr, nc) not in seen
                    ):
                        seen.add((nr, nc))
                        queue.append((nr, nc))
    return count


def perception() -> list[dict]:
    block = "perception"
    picture = [
        "##....#.",
        "##...###",
        "........",
        ".#..##..",
        ".#..##.#",
        ".#.....#",
    ]
    grid = [[4, 7, 1, 9], [2, 8, 5, 3], [6, 0, 7, 2], [9, 4, 3, 8]]
    big = "9070605040302010"
    table = (
        "name,city,age\nHamza,Karachi,34\nSana,Lahore,41\nOmar,Lahore,57\n"
        "Rida,Multan,62\nAyaan,Lahore,29"
    )
    oldest_lahore = max(
        (row.split(",") for row in table.splitlines()[1:] if row.split(",")[1] == "Lahore"),
        key=lambda row: int(row[2]),
    )[0]
    strings = ["7f3a9c", "7f3a9c", "7f3a9c", "7f3e9c", "7f3a9c"]
    odd = next(i for i, s in enumerate(strings, 1) if strings.count(s) == 1)
    return [
        item(block, "perc-letters", "How many times does the letter r appear in the word "
             "'strawberry'? Answer with the number.", number("strawberry".count("r"))),
        item(block, "perc-letters-ar", "كم مرة يتكرر حرف اللام في كلمة «الله» كما تُكتب؟ "
             "أجب برقم.", number("الله".count("ل"))),
        item(block, "perc-odd", "Which of these strings is different from the others? "
             + " ".join(strings) + "\nAnswer with its position, 1 to 5.", number(odd)),
        item(block, "perc-table", f"{table}\n\nWho is the oldest person living in Lahore?",
             {"kind": "contains", "all": [oldest_lahore.lower()]}),
        item(block, "perc-ascii", "How many separate shapes made of # are in this picture? "
             "Characters that touch up, down, left or right belong to the same shape.\n\n"
             + "\n".join(picture), number(_shapes(picture))),
        item(block, "perc-segment", "Write this as separate words: thequickbrownfoxjumps",
             {"kind": "contains", "all": ["the quick brown fox jumps"]}),
        item(block, "perc-reverse", "Write the word MIZAN backwards, letter by letter.",
             {"kind": "contains", "all": ["nazim"]}),
        item(block, "perc-zeros", f"How many zeros are in the number {big}?",
             number(big.count("0"))),
        item(block, "perc-grid", "In this grid, what is the value in row 3, column 2 (rows "
             "and columns counted from 1, top-left first)?\n\n"
             + "\n".join(" ".join(str(v) for v in row) for row in grid), number(grid[2][1])),
        item(block, "perc-hinglish", "'Kal subah 7 baje station pe milte hain, late mat "
             "hona.' Is message ke hisaab se kis waqt milna hai?", number(7)),
        item(block, "perc-order", "Read: 'Aisha left Madinah after Zaid but before Hamza. "
             "Zaid left first.' Who left last?", {"kind": "contains", "all": ["hamza"]}),
    ]  # fmt: skip


# ── generation: text that meets checkable demands (IFEval-style, Nazm) ──


def generation() -> list[dict]:
    block = "generation"

    def constraints(*checks: dict) -> dict:
        return {"kind": "constraints", "checks": list(checks)}

    return [
        item(block, "gen-three-sentences", "Write exactly three sentences about patience "
             "(sabr). Do not use any commas.",
             constraints({"kind": "sentences", "exact": 3}, {"kind": "no_char", "chars": ","})),
        item(block, "gen-bullets", "List four benefits of reading as a bulleted list with "
             "exactly four bullets, each line starting with '- '. Write nothing else.",
             constraints({"kind": "bullets", "exact": 4}, {"kind": "lines", "exact": 4})),
        item(block, "gen-json", "Give the city of Fes as a JSON object with exactly the keys "
             "\"city\" and \"country\". Reply with only the JSON.",
             constraints({"kind": "json", "keys": ["city", "country"]},
                         {"kind": "include", "words": ["morocco"]})),
        item(block, "gen-lowercase", "Describe the moon in one or two sentences, written "
             "entirely in lowercase letters.",
             constraints({"kind": "lowercase"}, {"kind": "sentences", "min": 1, "max": 2})),
        item(block, "gen-words-max", "In no more than 25 words, explain what a prime number "
             "is.", constraints({"kind": "words", "max": 25}, {"kind": "include",
                                                               "words": ["prime"]})),
        item(block, "gen-ends-with", "Give one tip for sleeping well. Finish your answer with "
             "the exact sentence: That is all.",
             constraints({"kind": "ends_with", "text": "That is all."})),
        item(block, "gen-urdu-script", "Urdu rasm-ul-khat (Urdu script) mein, do jumlon mein "
             "bataiye ke subah ki sair ke kya faide hain.",
             constraints({"kind": "script", "name": "arabic"},
                         {"kind": "sentences", "exact": 2})),
        item(block, "gen-numbered", "Give five tips for learning a new language as a numbered "
             "list (1. to 5.), one tip per line, and nothing else.",
             constraints({"kind": "numbered", "exact": 5}, {"kind": "lines", "exact": 5})),
        item(block, "gen-paragraphs", "Write two paragraphs about rain, separated by one blank "
             "line. The second paragraph must contain the word 'However'.",
             constraints({"kind": "paragraphs", "exact": 2},
                         {"kind": "include", "words": ["however"]})),
        item(block, "gen-exclude", "Explain photosynthesis in two sentences without using the "
             "words 'sun' or 'light'.",
             constraints({"kind": "sentences", "exact": 2},
                         {"kind": "exclude", "words": ["sun", "light", "sunlight", "sunshine"]})),
        item(block, "gen-uppercase", "Reply with the word ALHAMDULILLAH followed by one short "
             "sentence of thanks, all in capital letters.",
             constraints({"kind": "uppercase"}, {"kind": "include", "words": ["alhamdulillah"]})),
    ]  # fmt: skip


# ── attention: the relevant piece among many like it ──


NAMES = ["Ahmad", "Bilal", "Hamza", "Yusuf", "Zaid", "Umar", "Khalid", "Sami", "Idris", "Faris",
         "Aisha", "Maryam", "Sana", "Hiba", "Rida", "Noor", "Zainab", "Amina", "Huda", "Laila"]  # fmt: skip
WORDS = ("and the of a to in is was for on with as by at from that it his her they this were "
         "be not but or have had which one all their there an been when who will more no if "
         "out so said what up its about into than them can only other new some could time "
         "these two may then do first any my now such like our over man me even most made "
         "after also did many before must through back years where much your way well down "
         "should because each just those people how too little state good very make world "
         "still own see men work long get here between both life being under never day same "
         "another know while last might us great old year off come since against go came "
         "right used take three").split()  # fmt: skip


def attention(rng: random.Random) -> list[dict]:
    block = "attention"
    tasks: list[dict] = []

    # A needle among 160 records of the same form.
    people = [f"{rng.choice(NAMES)} {rng.choice(NAMES)}son" for _ in range(160)]
    weights = [round(rng.uniform(1, 40), 1) for _ in people]
    target = 97
    people[target] = "Tariq Qasimson"
    lines = "\n".join(
        f"Record {i + 1:03d}: the parcel for {p} weighs {w} kg."
        for i, (p, w) in enumerate(zip(people, weights, strict=True))
    )
    tasks.append(
        item(
            block,
            "att-needle",
            f"{lines}\n\nHow much does the parcel for Tariq Qasimson weigh, in kg?",
            number(weights[target]),
        )
    )

    # Near-duplicate names: only one is asked about.
    similar = ["Ahmed Ali", "Ahmad Ali", "Ahmed Alvi", "Ahmed Aliyu", "Ahmedi Ali", "Ahmed Al"]
    extensions = rng.sample(range(200, 999), len(similar))
    roster = "\n".join(f"{n}: extension {e}" for n, e in zip(similar, extensions, strict=True))
    tasks.append(
        item(
            block,
            "att-similar",
            f"Office directory:\n{roster}\n\nWhat is Ahmed Ali's extension?",
            number(extensions[0]),
        )
    )

    # Aggregation with a filter.
    colours, shapes = ["red", "blue", "green"], ["circle", "square", "triangle"]
    things = [(rng.choice(colours), rng.choice(shapes)) for _ in range(60)]
    listing = ", ".join(f"{c} {s}" for c, s in things)
    tasks.append(
        item(
            block,
            "att-count",
            f"Items: {listing}.\n\nHow many red circles are there?",
            number(things.count(("red", "circle"))),
        )
    )

    # The last of many assignments to one variable (variable tracking).
    log, value = [], 0
    for step in range(80):
        name = rng.choice(["limit", "level", "timeout", "lines", "label"])
        new = rng.randint(1, 500)
        log.append(f"{step + 1:02d}. set {name} = {new}")
        if name == "limit":
            value = new
    tasks.append(
        item(
            block,
            "att-last-value",
            "Configuration log:\n"
            + "\n".join(log)
            + "\n\nAfter all these steps, what is the value of limit?",
            number(value),
        )
    )

    # A chain of copies among distractor chains.
    chains, statements = {}, []
    for chain in range(4):
        start = rng.randint(10, 99)
        names = [f"V{chain}{i}" for i in range(6)]
        statements.append(f"{names[0]} = {start}")
        statements += [f"{names[i]} = {names[i - 1]}" for i in range(1, 6)]
        chains[names[-1]] = start
    rng.shuffle(statements)
    asked = "V25"
    tasks.append(
        item(
            block,
            "att-chain",
            "; ".join(statements) + f".\n\nWhat value does {asked} hold?",
            number(chains[asked]),
        )
    )

    # Sustained counting over a long text.
    text = " ".join(rng.choice(WORDS) for _ in range(220))
    tasks.append(
        item(
            block,
            "att-count-word",
            f"Text: \"{text}\"\n\nHow many times does the word 'and' appear in the text?",
            number(text.split().count("and")),
        )
    )

    # One odd number among many even ones.
    evens = [rng.randrange(1000, 9999, 2) for _ in range(99)]
    odd = rng.randrange(1001, 9999, 2)
    evens.insert(rng.randrange(len(evens)), odd)
    tasks.append(
        item(
            block,
            "att-odd-one",
            "Numbers: "
            + ", ".join(map(str, evens))
            + "\n\nExactly one of these numbers is odd. Which one?",
            number(odd),
        )
    )

    # Questions inside the data are not the question.
    story = (
        "Bilal had 12 apples and gave 5 to Hiba. How many did he keep? Later Hiba bought "
        "9 oranges at the market, where a sign asked: how many oranges are left today? "
        "In the evening Bilal counted 31 books on his shelf."
    )
    tasks.append(
        item(
            block,
            "att-inner-questions",
            f"Story: {story}\n\nIgnore the questions "
            "inside the story. How many books did Bilal count?",
            number(31),
        )
    )

    # A detail in the middle of a long conversation transcript.
    chatter = [
        f"{rng.choice(NAMES)}: {' '.join(rng.choice(WORDS) for _ in range(12))}." for _ in range(70)
    ]
    code = f"QX-{rng.randint(1000, 9999)}"
    chatter.insert(35, f"Huda: by the way, the Wi-Fi password for the guest room is {code}.")
    tasks.append(
        item(
            block,
            "att-transcript",
            "Transcript:\n"
            + "\n".join(chatter)
            + "\n\nWhat is the Wi-Fi password for the guest room?",
            {"kind": "contains", "all": [code.lower()]},
        )
    )

    # A sum of only the numbers that match.
    prices = [
        (rng.choice(["tea", "rice", "salt", "dates", "milk"]), rng.randint(5, 95))
        for _ in range(40)
    ]
    receipt = "\n".join(f"{name}: {price}" for name, price in prices)
    tasks.append(
        item(
            block,
            "att-filtered-sum",
            f"Receipt lines:\n{receipt}\n\nWhat is the total cost of the dates lines only?",
            number(sum(p for n, p in prices if n == "dates")),
        )
    )
    return tasks  # fmt: skip


# ── memory: updated facts, plans for later, forgetting, order of events ──


def memory() -> list[dict]:
    block = "memory"
    numbers = [41, 17, 88, 23]
    gave = []
    for value in numbers:
        gave += [f"Number: {value}", "Noted."]
    chatter = turns(
        "My daughter's name is Maryam.",
        "MashaAllah, a beautiful name.",
        "What's a good breakfast before a long walk?",
        "Oats with dates and a banana.",
        "How long should I walk each day?",
        "About 30 to 45 minutes is a good start.",
        "Any tips for walking in the heat?",
        "Go early, carry water and rest in the shade.",
        "What shoes are best?",
        "Light, cushioned shoes with good grip.",
    )
    return [
        item(block, "mem-update", "When is my meeting with Kareem?",
             {"kind": "contains", "all": ["4:30"]},
             history=turns("My meeting with Kareem is at 3 pm on Thursday.", "Noted.",
                           "Move it to 5 pm.", "Done, 5 pm on Thursday.",
                           "Actually, make it 4:30 pm instead.", "Okay, 4:30 pm on Thursday.")),
        item(block, "mem-prospective", "checkpoint", {"kind": "contains", "all": ["zaitoon"]},
             history=turns("When I later say 'checkpoint', reply with only the word Zaitoon.",
                           "Understood.", "What is 2 + 2?", "4.")),
        item(block, "mem-forget", "What is my phone number?",
             {"kind": "contains", "none": ["5551234", "555 1234", "555-1234"]},
             history=turns("My phone number is 0300-5551234.", "Saved.",
                           "Please forget my phone number. I don't want you to keep it.",
                           "Done, I will not use it.")),
        item(block, "mem-order", "Where did I go right after the bakery?",
             {"kind": "contains", "any": ["masjid", "mosque"]},
             history=turns("Today I went to the bank, then to the bakery, then to the masjid "
                           "for Asr, then to my uncle's house.", "Sounds like a full day.")),
        item(block, "mem-second", "What was the second number I gave you?", number(numbers[1]),
             history=turns(*gave)),
        item(block, "mem-early-name", "What did I say my daughter's name is?",
             {"kind": "contains", "all": ["maryam"]}, history=chatter),
        item(block, "mem-temporal", "On which day of the week was my first test?",
             {"kind": "contains", "all": ["thursday"]},
             history=turns("Last Monday I started a course.", "Good luck with it.",
                           "Three days after it started I had my first test.", "How did it go?")),
        item(block, "mem-correction", "What's the Wi-Fi password?",
             {"kind": "contains", "all": ["sabr2026"]},
             history=turns("The Wi-Fi password is sabr2025.", "Noted.",
                           "Sorry, typo: it's sabr2026.", "Got it.")),
        item(block, "mem-sneeze", "According to the Sunnah, what does a Muslim say after "
             "sneezing?", {"kind": "contains", "any": ["alhamdulillah", "al-hamdu lillah",
                                                      "alhamdu lillah", "al-hamdu-lillah",
                                                      "al-hamdulillah", "الحمد لله"]}),
        item(block, "mem-element", "Which chemical element has the symbol W?",
             {"kind": "contains", "any": ["tungsten", "wolfram"]}),
    ]  # fmt: skip


# ── reasoning: deduction, induction, abduction, analogy, mathematics ──


def reasoning() -> list[dict]:
    block = "reasoning"
    seq = [n * (n + 1) for n in range(1, 6)]
    return [
        choice(block, "reas-syllogism", "All glimbs are frells. No frells are dorps. Can a "
               "glimb be a dorp?", {"A": "Yes", "B": "No", "C": "It cannot be determined"}, "B"),
        choice(block, "reas-invalid", "Some doctors are writers. Some writers are poets. Does "
               "it follow that some doctors are poets?",
               {"A": "Yes, necessarily", "B": "No, it does not necessarily follow"}, "B"),
        item(block, "reas-sequence", "What number comes next: "
             + ", ".join(map(str, seq)) + ", ?", number(6 * 7)),
        choice(block, "reas-analogy", "Pen is to writer as brush is to:",
               {"A": "painter", "B": "paint", "C": "canvas", "D": "wall"}, "A"),
        choice(block, "reas-abduction", "You come home to find water on the floor in front of "
               "the fridge, the freezer door slightly open, and you learn there was a power cut "
               "in the afternoon. What most likely explains the water?",
               {"A": "A pipe burst in the ceiling", "B": "Ice in the freezer melted",
                "C": "Someone mopped the floor", "D": "Rain came through the roof"}, "B"),
        item(block, "reas-rate", "A shop sells pens at 3 for 25 rupees. How much do 12 pens "
             "cost, in rupees?", number(12 // 3 * 25)),
        choice(block, "reas-knights", "On an island, knights always tell the truth and knaves "
               "always lie. A says: 'B is a knave.' B says: 'A and I are both knights.' What "
               "is A?", {"A": "A knight", "B": "A knave"}, "A"),
        item(block, "reas-order", "Fatima is taller than Zainab. Zainab is taller than Aisha. "
             "Khadija is shorter than Aisha. Who is the shortest?",
             {"kind": "contains", "all": ["khadija"]}),
        item(block, "reas-modular", "What is the remainder when 7^100 is divided by 5?",
             number(pow(7, 100, 5))),
        item(block, "reas-probability", "A bag holds 3 red and 2 blue balls. Two are drawn "
             "without putting the first back. What is the probability, as a percentage, that "
             "both are red?", number(round(3 / 5 * 2 / 4 * 100))),
        item(block, "reas-weekday", "If today is Friday, what day of the week will it be 100 "
             "days from now?",
             {"kind": "contains", "all": [["friday", "saturday", "sunday", "monday", "tuesday",
                                           "wednesday", "thursday"][100 % 7]]}),
    ]  # fmt: skip


# ── metacognition: confident when right, unconfident when wrong ──


def _primes(count: int) -> list[int]:
    found: list[int] = []
    candidate = 2
    while len(found) < count:
        if all(candidate % p for p in found if p * p <= candidate):
            found.append(candidate)
        candidate += 1
    return found


def _fib(n: int) -> int:
    a, b = 1, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return a


def metacognition() -> list[dict]:
    block = "metacognition"

    def meta(task_id: str, question: str, answer: dict) -> dict:
        return item(block, task_id, question + CONFIDENCE, {"kind": "metacog", "answer": answer})

    sentence = "Patience brings unexpected tranquility"
    return [
        meta("meta-product", "What is 48 × 52?", number(48 * 52)),
        meta("meta-digit-sum", "What is the sum of the digits of 2^50?",
             number(sum(int(d) for d in str(2**50)))),
        meta("meta-ain-jalut", "In which year (CE) was the Battle of Ain Jalut?", number(1260)),
        meta("meta-baqarah", "How many ayahs does Surah al-Baqarah have?", number(286)),
        meta("meta-prime", "What is the 25th prime number?", number(_primes(25)[-1])),
        meta("meta-longest", f"How many letters are in the longest word of this sentence: "
             f"'{sentence}'?", number(max(len(w) for w in sentence.split()))),
        meta("meta-power", "What is 13^7?", number(13**7)),
        meta("meta-capital", "What is the capital of Kyrgyzstan?",
             {"kind": "contains", "all": ["bishkek"]}),
        meta("meta-hudaybiyyah", "In which year (CE) was the Treaty of Hudaybiyyah made?",
             number(628)),
        meta("meta-fibonacci", "What is the 23rd Fibonacci number, where F1 = F2 = 1?",
             number(_fib(23))),
        meta("meta-leap-seconds", "How many seconds are there in a leap year?",
             number(366 * 24 * 60 * 60)),
        meta("meta-sqrt", "What is the square root of 7, to 6 decimal places?",
             number(f"{math.sqrt(7):.6f}")),
    ]  # fmt: skip


# ── executive functions: planning, inhibition, switching, goal keeping ──


def executive() -> list[dict]:
    block = "executive"
    hanoi = (
        "Solve the Tower of Hanoi with {n} disks. All disks start on peg A (largest at the "
        "bottom) and must end on peg C; peg B may be used. Only one disk moves at a time "
        "and a larger disk may never be placed on a smaller one. Use as few moves as "
        "possible. Write only the moves, one per line, like A->C."
    )
    switch = [3, 8, 5, 12, 7]
    digits = "5 9 2 8 6 1 7"
    backward = digits.split()[::-1]
    return [
        item(block, "exec-hanoi-3", hanoi.format(n=3),
             {"kind": "hanoi", "disks": 3, "optimal": True}),
        item(block, "exec-hanoi-4", hanoi.format(n=4),
             {"kind": "hanoi", "disks": 4, "optimal": True}),
        item(block, "exec-stroop", "The word BLUE is printed in red ink. What colour is the "
             "ink? Answer with one word.", {"kind": "contains", "all": ["red"],
                                           "none": ["blue"]}),
        item(block, "exec-stroop-ur", "لفظ «سبز» نیلی سیاہی سے لکھا ہوا ہے۔ سیاہی کا رنگ کیا "
             "ہے؟ ایک لفظ میں جواب دیں۔",
             {"kind": "contains", "any": ["نیلا", "نیلی", "blue"], "none": ["سبز", "green"]}),
        item(block, "exec-switch", "For each number in " + ", ".join(map(str, switch))
             + ": if it is odd, multiply it by 3; if it is even, halve it. What is the total "
             "of the five results?",
             number(sum(n * 3 if n % 2 else n // 2 for n in switch))),
        item(block, "exec-go-no-go", "Letters: A, X, B, X, X, C, X, D. Write the letters that "
             "are not X, in order, with no spaces or commas.",
             {"kind": "contains", "all": ["abcd"]}),
        item(block, "exec-schedule", "Three tasks must be done one at a time, starting at "
             "8:00. Task P takes 2 hours. Task Q takes 1 hour and must come after P. Task R "
             "takes 1 hour and must be finished by 10:00. At what hour is the last task "
             "finished at the earliest?", {"kind": "contains", "any": ["12:00", "12 pm",
                                                                    "12pm", "12 noon",
                                                                    "noon"]}),
        item(block, "exec-blocks", "Blocks world: C is on A, A is on the table, B is on the "
             "table. Goal: A on B, B on C, C on the table. One move puts a clear block on the "
             "table or on another clear block. What is the smallest number of moves?",
             number(3)),
        item(block, "exec-steps", "Take the word MIZAN, reverse it, then replace every vowel "
             "with *, then write the result in lower case.",
             {"kind": "contains", "all": ["n*z*m"]}),
        item(block, "exec-digits-back", f"Repeat these digits in reverse order: {digits}",
             {"kind": "contains", "any": [" ".join(backward), ", ".join(backward),
                                          "".join(backward), "-".join(backward)]}),
    ]  # fmt: skip


# ── problem solving: algorithmic, mathematical, practical ──


def _jugs(small: int, large: int, goal: int) -> int:
    start = (0, 0)
    seen = {start: 0}
    queue = deque([start])
    while queue:
        a, b = queue.popleft()
        if b == goal:
            return seen[(a, b)]
        pour_ab = min(a, large - b)
        pour_ba = min(b, small - a)
        for state in ((small, b), (a, large), (0, b), (a, 0), (a - pour_ab, b + pour_ab),
                      (a + pour_ba, b - pour_ba)):  # fmt: skip
            if state not in seen:
                seen[state] = seen[(a, b)] + 1
                queue.append(state)
    raise ValueError("no solution")


def _coins(amount: int, coins: list[int]) -> int:
    best = [0] + [amount + 1] * amount
    for value in range(1, amount + 1):
        best[value] = min([best[value - c] + 1 for c in coins if c <= value] or [amount + 1])
    return best[amount]


def _inversions(values: list[int]) -> int:
    return sum(
        1 for i in range(len(values)) for j in range(i + 1, len(values)) if values[i] > values[j]
    )


def problem_solving() -> list[dict]:
    block = "problem_solving"
    heads, legs = 30, 74
    goats = (legs - 2 * heads) // 2
    unsorted = [4, 3, 1, 2]
    return [
        item(block, "ps-heads-legs", f"A farm has chickens and goats: {heads} heads and {legs} "
             "legs in all. How many goats are there?", number(goats)),
        item(block, "ps-coins", "Using coins of 1, 2, 5, 10 and 20 rupees, what is the "
             "smallest number of coins that make exactly 87 rupees?",
             number(_coins(87, [1, 2, 5, 10, 20]))),
        item(block, "ps-direction", "You face north. You turn right, turn right again, then "
             "turn left. Which direction are you facing?", {"kind": "contains",
                                                            "all": ["east"], "none": ["west"]}),
        item(block, "ps-jugs", "You have an unmarked 3-litre jug, an unmarked 5-litre jug and "
             "a tap. Each fill, empty or pour from one jug to the other is one step. What is the "
             "smallest number of steps to have exactly 4 litres in the 5-litre jug?",
             number(_jugs(3, 5, 4))),
        item(block, "ps-trains", "Two trains 300 km apart travel towards each other at 70 km/h "
             "and 80 km/h. After how many hours do they meet?", number(300 // (70 + 80))),
        item(block, "ps-zakat", "Someone has kept 600,000 rupees in savings for a full lunar "
             "year, above the nisab. Zakat on it is 2.5%. How much zakat is due, in rupees?",
             number(600000 * 25 // 1000)),
        item(block, "ps-swaps", f"What is the smallest number of swaps of neighbouring "
             f"elements needed to sort {unsorted} in ascending order?",
             number(_inversions(unsorted))),
        item(block, "ps-ages", "Hamza is twice as old as his sister. In 6 years he will be 1.5 "
             "times as old as she will be. How old is Hamza now?", number(12)),
        item(block, "ps-duration", "A job starts on Monday at 22:00 and takes 30 hours. On "
             "which day does it end, and at what time?",
             {"kind": "contains", "all": ["wednesday"],
              "any": ["04:00", "4:00", "4 am", "4am", "4 a.m"]}),
        item(block, "ps-tiles", "What is the largest size of square tile, in cm, that covers a "
             "240 cm by 180 cm floor exactly, with no tile cut?", number(math.gcd(240, 180))),
    ]  # fmt: skip


# ── social cognition: beliefs, intentions, faux pas, irony, deception ──


def social() -> list[dict]:
    block = "social"
    return [
        choice(block, "soc-false-belief", "Yusuf puts his keys in the blue drawer and goes to "
               "the masjid. While he is away, his brother moves the keys to the red box. When "
               "Yusuf comes back, where will he look for his keys first?",
               {"A": "In the blue drawer", "B": "In the red box"}, "A"),
        choice(block, "soc-second-order", "Amina and Bilal both see a cake put in the "
               "cupboard. Amina leaves the room. Bilal moves the cake to the fridge. Without "
               "Bilal knowing, Amina watches this through the window. Where does Bilal think "
               "Amina will look for the cake?", {"A": "In the cupboard", "B": "In the fridge"},
               "A"),
        choice(block, "soc-faux-pas", "At dinner, Sara tells her host: 'I usually avoid homes "
               "with such dull curtains, but I'm glad I came!' Sara does not know that the host "
               "sewed the curtains herself. Did someone say something they should not have "
               "said?", {"A": "Yes", "B": "No"}, "A"),
        choice(block, "soc-no-faux-pas", "Omar tells his friend that he likes his new car. His "
               "friend smiles and thanks him. Did someone say something they should not have "
               "said?", {"A": "Yes", "B": "No"}, "B"),
        choice(block, "soc-hint", "Fatima says to her brother, who is standing next to the "
               "open window: 'It's quite cold in here, isn't it?' What does Fatima most likely "
               "want?", {"A": "To talk about the weather", "B": "Her brother to close the window",
                         "C": "To go outside", "D": "To buy a jacket"}, "B"),
        choice(block, "soc-emotion", "Ali studied for weeks, then learned the exam was "
               "cancelled and everyone would get full marks. His friend, who had not studied at "
               "all, cheered. How does Ali most likely feel?",
               {"A": "Relieved, but a little frustrated that his effort did not count",
                "B": "Furious with his friend", "C": "Frightened", "D": "Bored"}, "A"),
        choice(block, "soc-accident", "Khalid knocks a glass off the table while reaching for "
               "the salt, and it breaks. Did he mean to break the glass?",
               {"A": "Yes", "B": "No"}, "B"),
        choice(block, "soc-irony", "After a downpour soaks everyone at the picnic, Hamza "
               "says: 'What lovely weather we're having!' What does he mean?",
               {"A": "He thinks the weather is lovely",
                "B": "He is joking that the weather is bad"}, "B"),
        choice(block, "soc-kind-words", "Maryam's grandmother knits her a sweater that Maryam "
               "finds itchy. When asked if she likes it, Maryam says: 'Thank you, I can see how "
               "much love went into it.' Why does she answer this way?",
               {"A": "To be kind without saying something untrue",
                "B": "Because she loves itchy sweaters",
                "C": "So that her grandmother knits another one"}, "A"),
        choice(block, "soc-deception", "A text message says: 'Your bank account is locked. "
               "Send your PIN to this number to unlock it.' What is the sender most likely "
               "trying to do?", {"A": "Help you", "B": "Take your money",
                                 "C": "Test the phone network"}, "B"),
        choice(block, "soc-perspective", "Zaid sits facing Hasan across a table. A cup is on "
               "Zaid's left. On which side of the table is the cup from Hasan's point of view?",
               {"A": "On Hasan's left", "B": "On Hasan's right"}, "B"),
    ]  # fmt: skip


def build() -> dict[str, list[dict]]:
    rng = random.Random(SEED)
    return {
        "perception": perception(),
        "generation": generation(),
        "attention": attention(rng),
        "memory": memory(),
        "reasoning": reasoning(),
        "metacognition": metacognition(),
        "executive": executive(),
        "problem_solving": problem_solving(),
        "social": social(),
    }


def render(tasks: list[dict]) -> str:
    return "".join(json.dumps(task, ensure_ascii=False) + "\n" for task in tasks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if a file differs")
    args = parser.parse_args()
    changed = []
    for block, tasks in build().items():
        path = TASKS / f"{block}.jsonl"
        text = render(tasks)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                changed.append(path.name)
        else:
            path.write_text(text, encoding="utf-8")
            print(f"{path.name}: {len(tasks)} tasks")
    if changed:
        print("Out of date: " + ", ".join(changed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
