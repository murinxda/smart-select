"""Text helpers shared with Universal Copy, which must give the same results as the app's."""

from __future__ import annotations

import re

# Any kind of space, the non-breaking ones included, as Android's regular expressions see \s
_SPACES = re.compile(r"[\s   -     　]+")


def normalize_spaces(text: str) -> str:
    return _SPACES.sub(" ", text)


def normalized(text: str) -> str:
    return normalize_spaces(text).strip()


def without_repeats(texts: list[str]) -> list[int]:
    """The indexes of the blocks to count: what the capture reads twice in a row, like a link and the
    text inside it, counts once.

    A text that the page itself repeats further down, like a headline shown twice, is not a repeat
    here: it counts by its own label.
    """
    return [index for index in range(len(texts)) if index == 0 or normalized(texts[index]) != normalized(texts[index - 1])]


def length(text: str) -> int:
    """The length in characters of a block, without its surrounding spaces.

    Universal Copy counts UTF-16 units instead: an emoji counts twice there, once here.
    """
    return len(text.strip())
