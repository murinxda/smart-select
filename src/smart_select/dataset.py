"""Pages and their labels, stored one page per line in JSONL files.

A page is what Universal Copy reads from a screen: its text blocks in reading order, with their
position in pixels. Each block has a label:

- ``article``: what the person opened the screen to read, which must be kept;
- ``optional``: either way is fine, like a caption or the date;
- ``noise``: menus, ads, other articles, which should go.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Literal

Label = Literal["article", "optional", "noise"]
LABELS: tuple[Label, ...] = ("article", "optional", "noise")


@dataclass(frozen=True)
class Block:
    text: str
    left: int
    right: int
    top: int


@dataclass(frozen=True)
class Page:
    id: str
    app: str
    screen_width: int
    # Unknown for the first pages captured on a phone, which only saved the width
    screen_height: int | None
    blocks: list[Block]
    labels: list[Label]
    # Where the page comes from and under which license, so that each dataset keeps its sources'
    source: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.labels) != len(self.blocks):
            raise ValueError(f"{self.id}: {len(self.labels)} labels for {len(self.blocks)} blocks")
        unknown = set(self.labels) - set(LABELS)
        if unknown:
            raise ValueError(f"{self.id}: unknown labels {sorted(unknown)}")

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> Page:
        return cls(
            id=data["id"],
            app=data["app"],
            screen_width=data["screen_width"],
            screen_height=data.get("screen_height"),
            blocks=[Block(**block) for block in data["blocks"]],
            labels=list(data["labels"]),
            source=dict(data.get("source", {})),
        )


def read_pages(path: Path) -> list[Page]:
    with path.open(encoding="utf-8") as lines:
        return [Page.from_json(json.loads(line)) for line in lines if line.strip()]


def write_pages(pages: Iterable[Page], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for page in pages:
            out.write(json.dumps(page.to_json(), ensure_ascii=False) + "\n")


Predictions = dict[str, list[int]]
"""For each page id, the indexes of the blocks a system kept."""


def read_predictions(path: Path) -> tuple[str, Predictions]:
    """A file ``{"system": "<name>", "pages": {"<page id>": [<kept block indexes>]}}``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["system"], {page: list(kept) for page, kept in data["pages"].items()}


def write_predictions(system: str, predictions: Predictions, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"system": system, "pages": {page: sorted(kept) for page, kept in predictions.items()}}
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
