"""Training examples for fine-tuning a model on smart select, in the chat format ``mlx_lm.lora`` reads.

Each example is one window of a labelled page, asked exactly as ``prompting`` asks it: the same
instructions, the same short example, the same "main content starts with" line after the first window.
The answer to learn is the numbers of the window's article blocks. Optional blocks are left out of it:
they do not count in the score, and leaving them out gives the model one thing to learn.

A page is cut twice: in windows as at inference, and once more shifted by half a window, so that each
block is also seen with other blocks around it, and at another place in its window.
"""

from __future__ import annotations

import json
from pathlib import Path

from smart_select.dataset import Page
from smart_select.prompting import CONTINUATION, INSTRUCTIONS, MAX_BLOCK_CHARS, MIN_START_CHARS, example_turns, numbered, ranges, windows
from smart_select.text import normalized


def cuts(page: Page) -> list[list[list[int]]]:
    """The page's windows as at inference, and the same shifted by half a window."""
    texts = [block.text for block in page.blocks]
    plain = windows(texts)
    if len(plain) < 2 and len(plain[0]) < 20:
        return [plain]
    half = len(plain[0]) // 2
    rest = sum(plain, [])[half:]
    shifted = [plain[0][:half]] + [[rest[i] for i in window] for window in windows([texts[i] for i in rest])]
    return [plain, shifted]


def examples(page: Page) -> list[dict]:
    """One chat per window: the prompt, and the numbers of the window's article blocks."""
    texts = [block.text for block in page.blocks]
    system = {"role": "system", "content": INSTRUCTIONS.format(width=page.screen_width)}
    out = []
    for cut in cuts(page):
        kept: list[int] = []
        for window in cut:
            start = next((normalized(texts[i]) for i in kept if len(normalized(texts[i])) >= MIN_START_CHARS),
                         normalized(texts[kept[0]]) if kept else None)
            prompt = (CONTINUATION.format(start=start[:MAX_BLOCK_CHARS]) if start else "") + "Blocks:\n" + numbered(page, window)
            article = [number for number, index in enumerate(window, start=1) if page.labels[index] == "article"]
            answer = "Answer: " + (ranges(article) or "none")
            out.append({"messages": [system, *example_turns(None), {"role": "user", "content": prompt},
                                     {"role": "assistant", "content": answer}]})
            kept += [window[number - 1] for number in article]
    return out


def write_examples(pages: list[Page], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as out:
        for page in pages:
            for example in examples(page):
                out.write(json.dumps(example, ensure_ascii=False) + "\n")
                count += 1
    return count
