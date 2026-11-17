"""What the rule labellers of pages labelled by hand once share: the labels of the first capture, found
again by text in a new capture of the page, and the blocks a capture reads again after a scroll.

The first captures (data/raw-pr40-first) were labelled block by block in commit a097f5d. The pages
were captured again with Wikimedia's sections unfolded and Universal Copy's harvest fixed: most
blocks are the same text, and keep their label.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIRST_LABELS = "a097f5d"


def parse(ranges: str) -> set[int]:
    out = set()
    for part in filter(None, ranges.split(",")):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def ranges(values: set[int]) -> str:
    out, values, i = [], sorted(values), 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[j + 1] == values[j] + 1:
            j += 1
        out.append(str(values[i]) if i == j else f"{values[i]}-{values[j]}")
        i = j + 1
    return ",".join(out)


def texts(page: str) -> list[str]:
    return [" ".join(b["text"].split()) for b in json.load(open(ROOT / "data/raw" / f"{page}.json"))["harvest"]]


class FirstLabels:
    """The labels of each text's readings in the first capture: the k-th reading of a text in the new
    capture has the label of its k-th reading in the first one, or of its last."""

    def __init__(self, page: str) -> None:
        self.by_text: dict[str, list[str]] = {}
        self.readings: dict[str, int] = {}
        old_file = ROOT / "data/raw-pr40-first" / f"{page}.json"
        if not old_file.exists():
            return
        label = json.loads(subprocess.run(["git", "-C", str(ROOT), "show", f"{FIRST_LABELS}:data/labels/{page}.json"],
                                          capture_output=True, text=True, check=True).stdout)
        article, optional = parse(label["article"]), parse(label["optional"])
        for i, block in enumerate(json.load(open(old_file))["harvest"]):
            self.by_text.setdefault(" ".join(block["text"].split()), []).append(
                "A" if i in article else "o" if i in optional else ".")

    def next(self, text: str) -> str | None:
        """The label of this reading of text in the first capture, None when it had no such text."""
        first = self.by_text.get(text, [])
        k = self.readings.get(text, 0)
        self.readings[text] = k + 1
        return first[min(k, len(first) - 1)] if first else None


def reread(texts: list[str], i: int) -> bool:
    """Whether block i, read before, is read again after a scroll: a long text, or a short one read with
    the same block before or after it. A short text can also be on the page several times, like the
    "last updated" line of each listing or a number in a table."""
    if len(texts[i]) > 80:
        return True
    before = texts[i - 1] if i > 0 else None
    after = texts[i + 1] if i + 1 < len(texts) else None
    return any(texts[j] == texts[i] and ((j > 0 and texts[j - 1] == before) or texts[j + 1] == after)
               for j in range(i))


def shingles(text: str) -> set[tuple[str, ...]]:
    words = re.sub(r"\[\d+\]", "", text).split()
    return {tuple(words[k:k + 6]) for k in range(len(words) - 5)}


def drop_rereads(texts: list[str], labels: list[str]) -> None:
    """Text read before, again after a scroll in another form: a paragraph with a footnote mark below
    the screen, or cut at another line as it crosses the screen's edge. Noise when nearly all of its
    runs of 6 words are in the article blocks before it."""
    read: set[tuple[str, ...]] = set()
    for i, text in enumerate(texts):
        runs = shingles(text)
        if labels[i] == "A" and len(text) > 40 and runs and len(runs & read) >= 0.9 * len(runs):
            labels[i] = "."
        if labels[i] == "A":
            read |= runs


def write(page: str, texts: list[str], labels: list[str]) -> None:
    """Writes the page's label file, and with --show, prints each block with its label."""
    if "--show" in sys.argv:
        for i, (text, label) in enumerate(zip(texts, labels)):
            print(f"{label} {i:4d} {text[:110]}")
    article = {i for i, label in enumerate(labels) if label == "A"}
    optional = {i for i, label in enumerate(labels) if label == "o"}
    out = {"article": ranges(article), "optional": ranges(optional), "labelled_by": "Claude, by rules", "checked_by": None}
    (ROOT / "data/labels" / f"{page}.json").write_text(json.dumps(out) + "\n")
    print(f"{page}: {len(texts)} blocks, {len(article)} article, {len(optional)} optional")
