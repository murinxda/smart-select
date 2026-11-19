"""The open dataset: pages captured from openly licensed sites, labelled by hand.

Raw captures (``data/raw/<id>.json``, with a screenshot of each screen) stay out of git. Labels are
small files, ``data/labels/<id>.json``, the dataset's source of truth::

    {"article": "16-40,45", "optional": "13-15", "labelled_by": "Claude", "checked_by": null}

Blocks outside both ranges are noise. ``build`` combines both into the training and validation sets.
"""

from __future__ import annotations

import json
from pathlib import Path

from smart_select.dataset import Page, write_pages
from smart_select.universal_copy import read_capture

# Whole sites the training set never sees, so that validation measures pages from new sites. Recipes
# all come from one site: a few of them are held out instead.
VALIDATION_SITES = (
    "android-", "wikivoyage-fr-", "globalvoices-fr-", "cooking-", "superuser-", "french-",
    "wikipedia-it-", "wikipedia-nl-",
)
VALIDATION_RECIPES = 3
# Pages left out of both sets: Universal Copy reads their math formulas one symbol a block, out of order,
# so no label can say what a person would copy
EXCLUDED = ("wikipedia-es-superficie-de-riemann", "wikipedia-fr-hauteur-geometrie-algebrique")


def is_validation(page_id: str, recipe_index: int | None) -> bool:
    return page_id.startswith(VALIDATION_SITES) or (recipe_index is not None and recipe_index < VALIDATION_RECIPES)


def show(raw: Path, width: int = 110) -> str:
    """A captured page, one block a line, to label it: index, left and top in pixels, text."""
    data = json.loads(raw.read_text(encoding="utf-8"))
    blocks = data.get("harvest") or data["screen"]
    lines = [f"{raw.stem}  {data.get('url', '')}  {len(blocks)} blocks, {'end' if data.get('reachedEnd') else 'cut'}"]
    for index, block in enumerate(blocks):
        text = " ".join(block["text"].split())
        lines.append(f"{index:4} {block['left']:4} {block['top']:5} {text[:width]}")
    return "\n".join(lines)


def build(raw: Path, labels: Path, out: Path) -> tuple[list[Page], list[Page], list[str]]:
    """Writes ``out/train.jsonl`` and ``out/validation.jsonl``. Returns both sets, and the ids of the
    captures without labels yet."""
    train, validation, unlabelled = [], [], []
    recipes = 0
    for capture in sorted(raw.glob("*.json")):
        if capture.stem in EXCLUDED:
            continue
        label_file = labels / capture.name
        if not label_file.exists():
            unlabelled.append(capture.stem)
            continue
        label_data = json.loads(label_file.read_text(encoding="utf-8"))
        page = read_capture(capture, {}, label_data)
        recipe_index = None
        if page.source.get("category") == "recipe":
            recipe_index, recipes = recipes, recipes + 1
        (validation if is_validation(page.id, recipe_index) else train).append(page)
    write_pages(train, out / "train.jsonl")
    write_pages(validation, out / "validation.jsonl")
    return train, validation, unlabelled
