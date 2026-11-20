"""Smart select by prompting a model, without training it: the baseline that fine-tuning must beat.

A page is cut in windows of consecutive blocks, like the app cuts it in batches for Gemini Nano. Each
window is one prompt: the instructions, then the window's blocks, numbered from 1, with their left and
right edges. The model answers with the numbers of the blocks to keep (``Answer: 3-7, 9``). After the
first window, the prompt also says how the main content starts, so that a window holding only ads or
other articles is not taken for an article of its own.

The prompt follows the app's (``SmartSelectionPrompt.kt``), with two changes for this project's labels:
the blocks' positions, and "when unsure, keep it", since a page missing part of its article counts as
failed.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable

from smart_select.dataset import Page, Predictions
from smart_select.text import normalized, without_repeats

MAX_WINDOW_BLOCKS = 100
MAX_WINDOW_CHARS = 8000
MAX_BLOCK_CHARS = 300
# A block's own line: its number, its edges, and its text
LINE_CHARS = 16
MIN_START_CHARS = 40

INSTRUCTIONS = """\
You select the main content of a phone screen for a copy tool. You get the text blocks read from the \
screen, numbered, in reading order. Each block starts with its left and right edges in pixels, on a \
screen {width} pixels wide.

Give the numbers of the blocks that make up the main content: what the person opened this screen to \
read. Keep the title, the paragraphs, the headings, lists and quotes of the article; in documentation, \
the code too; on a question and answer page, the question and every answer. A sentence can be split \
over several blocks because of links: keep all its pieces.

Never keep: the name of the site, menus, search, sign in, tabs, buttons (edit, share, save), \
breadcrumbs, cookie banners, ads, related or other articles, tags, comments, references, external \
links and the footer. Captions, the date and the author, tables and summary boxes can go either way.

The main content usually lines up in one column: side columns and boxes have other edges. When unsure \
whether a block belongs to the main content, keep it: missing part of the article is worse than \
keeping a little more.

Answer with the numbers only, and ranges for consecutive blocks, like:
Answer: 3-7, 9, 12-20
If no block is main content, answer:
Answer: none"""

CONTINUATION = """\
These blocks come further down the same page. Its main content starts with: "{start}"
Only keep what continues that same article. Other articles and ads are not main content: if nothing \
continues it, answer none.

"""

# A short news screen, in the spirit of the app's own examples
TOY_EXAMPLE = (
    "1. (42-300) MyNews\n2. (900-1040) Sign in\n3. (42-1038) Home > World\n4. (42-1038) Storm hits the coast\n"
    "5. (42-1038) Published on 5 May\n6. (42-1038) A storm hit the coast on Monday, according to\n"
    "7. (300-620) the weather service\n8. (42-1038) , and closed several roads.\n9. (42-1038) Sponsored\n"
    "10. (42-1038) Read also: Floods in the north",
    "Answer: 4, 6-8",
)

Ask = Callable[[list[dict[str, str]]], str]
"""Sends chat messages to a model, returns its answer."""


def windows(texts: list[str]) -> list[list[int]]:
    """Cuts a page in windows of consecutive blocks. The text a capture reads twice in a row, like a link
    and the text inside it, is sent once."""
    out: list[list[int]] = []
    window: list[int] = []
    chars = 0
    for index in without_repeats(texts):
        size = min(len(normalized(texts[index])), MAX_BLOCK_CHARS) + LINE_CHARS
        if window and (chars + size > MAX_WINDOW_CHARS or len(window) == MAX_WINDOW_BLOCKS):
            out.append(window)
            window, chars = [], 0
        window.append(index)
        chars += size
    if window:
        out.append(window)
    return out


def numbered(page: Page, window: list[int]) -> str:
    lines = []
    for number, index in enumerate(window, start=1):
        block = page.blocks[index]
        lines.append(f"{number}. ({block.left}-{block.right}) {normalized(block.text)[:MAX_BLOCK_CHARS]}")
    return "\n".join(lines)


ANSWER = re.compile(r"answer\s*:", re.I)
NUMBERS = re.compile(r"(\d+)\s*(?:-|–|to)\s*(\d+)|(\d+)")


def read_answer(answer: str, count: int) -> list[int] | None:
    """The numbers an answer gives, from 1 to count; None when it gives none that can be read. Numbers
    the model made up, out of the window, are dropped."""
    found = list(ANSWER.finditer(answer))
    text = answer[found[-1].end():] if found else answer
    if re.match(r"\s*none\b", text, re.I):
        return []
    numbers: set[int] = set()
    for match in NUMBERS.finditer(text):
        if match.group(3):
            numbers.add(int(match.group(3)))
        else:
            first, last = int(match.group(1)), int(match.group(2))
            numbers.update(range(first, min(last, count) + 1))
    numbers = {number for number in numbers if 1 <= number <= count}
    if not numbers and not re.search(r"\d", text):
        return None
    return sorted(numbers)


def example_turns(example: Page | None) -> list[dict[str, str]]:
    """The example shown before the page: the toy news screen, and with one-shot, a real labelled window."""
    turns = [{"role": "user", "content": "Blocks:\n" + TOY_EXAMPLE[0]}, {"role": "assistant", "content": TOY_EXAMPLE[1]}]
    if example is not None:
        window = windows([block.text for block in example.blocks])[0][:40]
        kept = [number for number, index in enumerate(window, start=1) if example.labels[index] == "article"]
        turns += [{"role": "user", "content": "Blocks:\n" + numbered(example, window)},
                  {"role": "assistant", "content": "Answer: " + (ranges(kept) or "none")}]
    return turns


def ranges(numbers: list[int]) -> str:
    out: list[str] = []
    for number in sorted(numbers):
        if out and "-" not in out[-1] and int(out[-1]) == number - 1:
            out[-1] = f"{out[-1]}-{number}"
        elif out and "-" in out[-1] and int(out[-1].split("-")[1]) == number - 1:
            out[-1] = f"{out[-1].split('-')[0]}-{number}"
        else:
            out.append(str(number))
    return ", ".join(out)


@dataclass
class PageRun:
    page: str
    kept: list[int]
    windows: int
    unreadable: int
    seconds: float
    answers: list[str] = field(default_factory=list)


def select(page: Page, ask: Ask, example: Page | None = None) -> PageRun:
    """Asks the model about each window of the page; returns the indexes of the blocks it kept, with
    the blocks read twice in a row kept along with their first reading."""
    texts = [block.text for block in page.blocks]
    system = {"role": "system", "content": INSTRUCTIONS.format(width=page.screen_width)}
    kept: list[int] = []
    answers: list[str] = []
    unreadable = 0
    started = time.monotonic()
    page_windows = windows(texts)
    for window in page_windows:
        start = next((normalized(texts[i]) for i in kept if len(normalized(texts[i])) >= MIN_START_CHARS),
                     normalized(texts[kept[0]]) if kept else None)
        prompt = (CONTINUATION.format(start=start[:MAX_BLOCK_CHARS]) if start else "") + "Blocks:\n" + numbered(page, window)
        answer = ask([system, *example_turns(example), {"role": "user", "content": prompt}])
        answers.append(answer)
        numbers = read_answer(answer, len(window))
        if numbers is None:
            unreadable += 1
            continue
        kept += [window[number - 1] for number in numbers]
    # A text read twice in a row was sent once: its second reading follows the first
    chosen = set(kept)
    for index in range(1, len(texts)):
        if index - 1 in chosen and normalized(texts[index]) == normalized(texts[index - 1]):
            chosen.add(index)
    return PageRun(page.id, sorted(chosen), len(page_windows), unreadable, time.monotonic() - started, answers)


def mlx_model(name: str, max_tokens: int = 400) -> Ask:
    """A model run on this Mac with MLX, answering without sampling: the same prompt gives the same answer."""
    from mlx_lm import generate, load

    model, tokenizer = load(name, tokenizer_config={"fix_mistral_regex": True})

    def ask(messages: list[dict[str, str]]) -> str:
        prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens)

    return ask


def predictions(runs: list[PageRun]) -> Predictions:
    return {run.page: run.kept for run in runs}
