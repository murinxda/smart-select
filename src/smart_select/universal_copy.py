"""Imports the pages captured and labelled in Universal Copy.

A debug build of the app saves each screen it reads as JSON: the blocks of the screen, and in
harvest mode the blocks of every screen the person scrolled through. Labels were added by hand as
ranges of block indexes, ``{"article": "4,19-58", "optional": "59"}``, the rest being noise.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from smart_select.dataset import Block, Label, Page


def read_capture(path: Path, source: dict[str, str]) -> Page | None:
    """The labelled page in a capture file, or None if it has no labels yet."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if "labels" not in data:
        return None
    # The harvest holds every screen of the page; a single screen otherwise
    blocks = data.get("harvest") or data["screen"]
    article = _indexes(data["labels"].get("article", ""))
    optional = _indexes(data["labels"].get("optional", ""))

    def label(index: int) -> Label:
        return "article" if index in article else "optional" if index in optional else "noise"

    return Page(
        id=path.stem,
        app=data["package"],
        screen_width=data["screenWidth"],
        screen_height=data.get("screenHeight"),
        blocks=[Block(block["text"], block["left"], block["right"], block["top"]) for block in blocks],
        labels=[label(index) for index in range(len(blocks))],
        source=dict(source, **({"url": data["url"]} if "url" in data else {})),
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


def _indexes(ranges: str) -> set[int]:
    indexes: set[int] = set()
    for part in filter(None, (part.strip() for part in ranges.split(","))):
        bounds = [int(bound) for bound in part.split("-")]
        indexes.update(range(bounds[0], bounds[-1] + 1))
    return indexes
