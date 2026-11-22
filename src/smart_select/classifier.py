"""Smart select by a small classifier that scores each block of a page, as article or not.

Each block becomes a vector: what its text means, from a frozen multilingual sentence encoder
(multilingual-e5-small), and where it sits on screen. A small bidirectional GRU then reads the page's
blocks in order, so that each block is judged with its neighbours: a short line is a heading between
two paragraphs, and a menu item among other links. The blocks scored above a threshold are kept.

Optional blocks do not count in the loss: either way is fine for them, as in the score. The number of
epochs and the threshold are chosen by cross-validation on the training pages, so that the
validation pages are only used to report the result.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from smart_select.dataset import Page, Predictions
from smart_select.scoring import score_system
from smart_select.text import normalized, without_repeats

if TYPE_CHECKING:
    import numpy as np
    import torch

ENCODER = "intfloat/multilingual-e5-small"
# Long enough for the start of a paragraph, which says what kind of block it is
MAX_TOKENS = 128
# A block this long is a paragraph: the left edge most of them share is the article's column
PARAGRAPH_CHARS = 80
POSITION_FEATURES = 7


def counted(page: Page) -> list[int]:
    """The blocks the classifier reads: what the capture reads twice in a row is read once, and its
    second reading gets the first one's answer, as in the scoring."""
    return without_repeats([block.text for block in page.blocks])


def position_features(page: Page) -> list[list[float]]:
    """For each counted block: its edges and width on the screen, how far its left edge is from the
    page's column, its length, and where it comes on the page."""
    indexes = counted(page)
    width = page.screen_width
    lefts = Counter(round(page.blocks[i].left / 10) * 10 for i in indexes
                    if len(normalized(page.blocks[i].text)) >= PARAGRAPH_CHARS)
    column = lefts.most_common(1)[0][0] if lefts else min(page.blocks[i].left for i in indexes)
    out = []
    for number, index in enumerate(indexes):
        block = page.blocks[index]
        out.append([
            block.left / width,
            block.right / width,
            (block.right - block.left) / width,
            (block.left - column) / width,
            float(abs(block.left - column) <= 10),
            math.log1p(len(normalized(block.text))) / 8,
            number / max(len(indexes) - 1, 1),
        ])
    return out


def targets(page: Page) -> tuple[list[float], list[float]]:
    """For each counted block: 1 for article, 0 for noise; and whether it counts in the loss."""
    labels = [page.labels[i] for i in counted(page)]
    return [float(label == "article") for label in labels], [float(label != "optional") for label in labels]


class Embeddings:
    """The encoder's vectors of the pages' blocks, computed once and kept in a file."""

    def __init__(self, cache: Path, encoder: str = ENCODER):
        self.cache = cache
        self.encoder = encoder
        self._model = None

    def __call__(self, pages: list[Page]) -> dict[str, np.ndarray]:
        import numpy as np

        stored = dict(np.load(self.cache)) if self.cache.exists() else {}
        missing = [page for page in pages if page.id not in stored]
        for page in missing:
            # e5 expects "query: " before a text compared with others of its kind
            texts = ["query: " + normalized(page.blocks[i].text) for i in counted(page)]
            stored[page.id] = self.model.encode(texts, batch_size=64, normalize_embeddings=True,
                                                convert_to_numpy=True).astype(np.float32)
        if missing:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez(self.cache, **stored)
        return {page.id: stored[page.id] for page in pages}

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.encoder)
            self._model.max_seq_length = MAX_TOKENS
        return self._model


@dataclass
class Settings:
    hidden: int = 64
    dropout: float = 0.3
    learning_rate: float = 1e-3
    epochs: int = 30
    seed: int = 0


def page_model(inputs: int, settings: Settings) -> torch.nn.Module:
    import torch
    from torch import nn

    class PageModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.project = nn.Sequential(nn.Dropout(settings.dropout), nn.Linear(inputs, 2 * settings.hidden), nn.GELU())
            self.read = nn.GRU(2 * settings.hidden, settings.hidden, batch_first=True, bidirectional=True)
            self.score = nn.Sequential(nn.Dropout(settings.dropout), nn.Linear(4 * settings.hidden, 1))

        def forward(self, blocks: torch.Tensor) -> torch.Tensor:
            """One page's blocks, (blocks, inputs) → one logit a block."""
            projected = self.project(blocks)
            read, _ = self.read(projected.unsqueeze(0))
            # The block itself, and what the GRU read around it
            return self.score(torch.cat([read.squeeze(0), projected], dim=-1)).squeeze(-1)

    return PageModel()


def inputs(page: Page, embeddings: dict[str, np.ndarray]) -> torch.Tensor:
    import numpy as np
    import torch

    return torch.from_numpy(np.concatenate([embeddings[page.id], np.array(position_features(page), dtype=np.float32)], axis=1))


def train(pages: list[Page], embeddings: dict[str, np.ndarray], settings: Settings,
          checkpoints: tuple[int, ...] = ()) -> dict[int, torch.nn.Module]:
    """Trains on the pages, one page a step; returns the model after each epoch in checkpoints, and
    at the end."""
    import copy

    import torch

    torch.manual_seed(settings.seed)
    order = random.Random(settings.seed)
    data = [(inputs(page, embeddings), *map(torch.tensor, targets(page))) for page in pages]
    model = page_model(data[0][0].shape[1], settings)
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings.learning_rate, weight_decay=0.01)
    loss = torch.nn.BCEWithLogitsLoss(reduction="none")
    out = {}
    for epoch in range(1, settings.epochs + 1):
        model.train()
        order.shuffle(data)
        for features, target, counts in data:
            optimizer.zero_grad()
            value = (loss(model(features), target) * counts).sum() / counts.sum().clamp(min=1)
            value.backward()
            optimizer.step()
        if epoch in checkpoints:
            out[epoch] = copy.deepcopy(model).eval()
    out[settings.epochs] = model.eval()
    return out


def scores(model: torch.nn.Module, pages: list[Page], embeddings: dict[str, np.ndarray]) -> dict[str, list[float]]:
    """For each page, each block's probability of being article, repeats included."""
    import torch

    out = {}
    with torch.no_grad():
        for page in pages:
            probabilities = torch.sigmoid(model(inputs(page, embeddings))).tolist()
            by_index = dict(zip(counted(page), probabilities))
            # A second reading gets the first one's score
            last = 0.0
            out[page.id] = [last := by_index.get(index, last) for index in range(len(page.blocks))]
    return out


def ensemble(pages: list[Page], embeddings: dict[str, np.ndarray], settings: Settings, tested: list[Page],
             seeds: int, checkpoints: tuple[int, ...] = ()) -> dict[int, dict[str, list[float]]]:
    """Trains one model a seed and averages their scores on the tested pages, after each epoch in
    checkpoints and at the end: on so few pages, one model's luck matters."""
    runs: dict[int, list[dict[str, list[float]]]] = {}
    for seed in range(seeds):
        models = train(pages, embeddings, Settings(**{**settings.__dict__, "seed": settings.seed + seed}), checkpoints)
        for epoch, model in models.items():
            runs.setdefault(epoch, []).append(scores(model, tested, embeddings))
    return {epoch: {page.id: [sum(run[page.id][i] for run in found) / len(found) for i in range(len(page.blocks))]
                    for page in tested}
            for epoch, found in runs.items()}


def kept(page_scores: dict[str, list[float]], threshold: float) -> Predictions:
    return {page: [i for i, score in enumerate(values) if score >= threshold] for page, values in page_scores.items()}


THRESHOLDS = [round(0.05 * i, 2) for i in range(1, 20)]


def best_threshold(pages: list[Page], page_scores: dict[str, list[float]]) -> tuple[float, int, float]:
    """The threshold that completes the most pages, then gives the best F2; with those two scores."""
    best = max(((score_system("", pages, kept(page_scores, t)), t) for t in THRESHOLDS),
               key=lambda found: (found[0].complete, found[0].f2, found[1]))
    return best[1], best[0].complete, best[0].f2


@dataclass
class CrossValidation:
    epochs: int
    threshold: float
    complete: int
    f2: float
    table: list[tuple[int, float, int, float]]


def cross_validate(pages: list[Page], embeddings: dict[str, np.ndarray], settings: Settings, seeds: int,
                   epochs: tuple[int, ...] = (5, 10, 20, 30), folds: int = 5) -> CrossValidation:
    """Trains on 4 fifths of the pages and scores the other fifth, five times; keeps the number of
    epochs and the threshold that do best on the pages each model did not see."""
    shuffled = sorted(pages, key=lambda page: page.id)
    random.Random(settings.seed).shuffle(shuffled)
    held: dict[int, dict[str, list[float]]] = {epoch: {} for epoch in epochs}
    for fold in range(folds):
        test = shuffled[fold::folds]
        tested = {page.id for page in test}
        rest = [page for page in shuffled if page.id not in tested]
        found = ensemble(rest, embeddings, Settings(**{**settings.__dict__, "epochs": max(epochs)}), test, seeds, epochs)
        for epoch in epochs:
            held[epoch].update(found[epoch])
    table = [(epoch, *best_threshold(pages, held[epoch])) for epoch in epochs]
    epoch, threshold, complete, f2 = max(table, key=lambda row: (row[2], row[3]))
    return CrossValidation(epoch, threshold, complete, f2, table)
