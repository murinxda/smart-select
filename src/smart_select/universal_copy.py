"""Imports the pages captured and labelled in Universal Copy.

A debug build of the app saves each screen it reads as JSON: the blocks of the screen, and in
harvest mode the blocks of every screen the person scrolled through. Labels were added by hand as
ranges of block indexes, ``{"article": "4,19-58", "optional": "59"}``, the rest being noise.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from smart_select.dataset import Block, Label, Page, Predictions


def read_capture(path: Path, source: dict[str, str], labels: dict[str, str] | None = None) -> Page | None:
    """The labelled page in a capture file, or None if it has no labels yet.

    :param labels: ranges of block indexes, when they are not in the capture itself
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    labels = labels if labels is not None else data.get("labels")
    if labels is None:
        return None
    # The harvest holds every screen of the page; a single screen otherwise
    blocks = data.get("harvest") or data["screen"]
    article = _indexes(labels.get("article", ""))
    optional = _indexes(labels.get("optional", ""))

    def label(index: int) -> Label:
        return "article" if index in article else "optional" if index in optional else "noise"

    return Page(
        id=path.stem,
        app=data["package"],
        screen_width=data["screenWidth"],
        screen_height=data.get("screenHeight"),
        blocks=[Block(block["text"], block["left"], block["right"], block["top"]) for block in blocks],
        labels=[label(index) for index in range(len(blocks))],
        source=dict(data.get("source", {}), **source, **({"url": data["url"]} if "url" in data else {})),
    )


def import_folder(samples: Path, out: Path, source: dict[str, str]) -> tuple[list[Page], list[Path]]:
    """Reads every labelled capture in ``samples``, and copies the predictions that Universal
    Copy's scoring test wrote in ``samples/predictions`` to ``out/predictions``."""
    captures = sorted(path for path in samples.glob("*.json") if not path.name.endswith(".answers.json"))
    pages = [page for page in (read_capture(path, source) for path in captures) if page is not None]
    copied = []
    for predictions in sorted((samples / "predictions").glob("*.json")):
        target = out / "predictions" / predictions.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(predictions, target)
        copied.append(target)
    return pages, copied


def write_samples(pages: list[Page], predictions: Predictions, out: Path) -> None:
    """Writes pages as Universal Copy's scoring test reads them, with a model's answers to replay: the
    app's position rules then run on what that model kept.

    The model was not asked the app's own prompts, so none is recorded: every question the rules ask,
    in both passes, gets what the model said about each block (``firstPass``), like a model that gives
    a block the same answer whenever it sees it.
    """
    out.mkdir(parents=True, exist_ok=True)
    for page in pages:
        labels = {"article": _ranges(i for i, label in enumerate(page.labels) if label == "article"),
                  "optional": _ranges(i for i, label in enumerate(page.labels) if label == "optional")}
        sample = {"name": page.id, "package": page.app, "screenWidth": page.screen_width, "screenHeight": page.screen_height,
                  "screen": [], "harvest": [{"text": b.text, "left": b.left, "right": b.right, "top": b.top} for b in page.blocks],
                  "labels": labels}
        (out / f"{page.id}.json").write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        kept = set(predictions.get(page.id, []))
        answers = {"prompts": {}, "firstPass": {str(i): i in kept for i in range(len(page.blocks))}}
        (out / f"{page.id}.answers.json").write_text(json.dumps(answers), encoding="utf-8")


def _ranges(indexes) -> str:
    out: list[list[int]] = []
    for index in sorted(indexes):
        if out and out[-1][1] == index - 1:
            out[-1][1] = index
        else:
            out.append([index, index])
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in out)


def _indexes(ranges: str) -> set[int]:
    indexes: set[int] = set()
    for part in filter(None, (part.strip() for part in ranges.split(","))):
        bounds = [int(bound) for bound in part.split("-")]
        indexes.update(range(bounds[0], bounds[-1] + 1))
    return indexes
