"""How well a selection keeps the article and leaves out the rest.

Smart select removes what is not worth copying, so a selection missing a part of the article is
worse than one keeping some noise. In order of importance:

1. complete pages: nothing labelled ``article`` is missing;
2. F2: the harmonic mean of the article found and the precision, the article found weighted twice;
3. the article found (recall) and the precision.

Everything is counted in characters, so that a paragraph weighs more than a label. All noise counts,
wherever it is on the page, and each block counts by its own label, except what the capture reads
twice in a row (see ``text.without_repeats``).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable

from smart_select.dataset import Page
from smart_select.text import length, without_repeats


@dataclass(frozen=True)
class PageScore:
    page: str
    article_chars: int
    article_kept: int
    noise_kept: int
    missed: list[int]
    wrongly_kept: list[int]

    @property
    def complete(self) -> bool:
        return not self.missed

    @property
    def recall(self) -> float:
        return 1.0 if self.article_chars == 0 else self.article_kept / self.article_chars

    @property
    def precision(self) -> float:
        kept = self.article_kept + self.noise_kept
        return 0.0 if kept == 0 else self.article_kept / kept

    @property
    def f2(self) -> float:
        recall, precision = self.recall, self.precision
        if recall + precision == 0:
            return 0.0
        return 5 * recall * precision / (4 * precision + recall)


def score_page(page: Page, kept: Iterable[int]) -> PageScore:
    kept = set(kept)
    counted = without_repeats([block.text for block in page.blocks])
    article = [index for index in counted if page.labels[index] == "article"]
    noise = [index for index in counted if page.labels[index] == "noise"]

    def chars(indexes: Iterable[int]) -> int:
        return sum(length(page.blocks[index].text) for index in indexes)

    return PageScore(
        page=page.id,
        article_chars=chars(article),
        article_kept=chars(index for index in article if index in kept),
        noise_kept=chars(index for index in noise if index in kept),
        missed=[index for index in article if index not in kept],
        wrongly_kept=[index for index in noise if index in kept],
    )


@dataclass(frozen=True)
class Summary:
    system: str
    pages: list[PageScore]

    @property
    def complete(self) -> int:
        return sum(score.complete for score in self.pages)

    @property
    def f2(self) -> float:
        return mean(score.f2 for score in self.pages)

    @property
    def recall(self) -> float:
        return mean(score.recall for score in self.pages)

    @property
    def precision(self) -> float:
        return mean(score.precision for score in self.pages)


def score_system(system: str, pages: list[Page], predictions: dict[str, list[int]]) -> Summary:
    """Scores every page; a page without a prediction counts as one where nothing was kept."""
    return Summary(system, [score_page(page, predictions.get(page.id, [])) for page in pages])
