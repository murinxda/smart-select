import pytest

from smart_select.dataset import Block, Page
from smart_select.scoring import score_page, score_system


def page(*blocks: tuple[str, str]) -> Page:
    """A page from (text, label) pairs."""
    return Page(
        id="page",
        app="com.android.chrome",
        screen_width=1080,
        screen_height=2400,
        blocks=[Block(text, 42, 1000, 100 * index) for index, (text, _) in enumerate(blocks)],
        labels=[label for _, label in blocks],
    )


ARTICLE = page(
    ("Menu", "noise"),
    ("Headline", "article"),
    ("Published today", "optional"),
    ("A paragraph.", "article"),
    ("Other news", "noise"),
)


def test_keeping_the_article_is_complete_and_exact():
    score = score_page(ARTICLE, [1, 3])

    assert score.complete
    assert (score.recall, score.precision, score.f2) == (1.0, 1.0, 1.0)


def test_optional_blocks_count_neither_way():
    assert score_page(ARTICLE, [1, 2, 3]).precision == 1.0


def test_missing_any_article_block_makes_the_page_incomplete():
    score = score_page(ARTICLE, [3])

    assert not score.complete
    assert score.missed == [1]
    assert score.recall == pytest.approx(12 / 20)


def test_noise_counts_in_characters():
    score = score_page(ARTICLE, [1, 3, 4])

    assert score.noise_kept == len("Other news")
    assert score.precision == pytest.approx(20 / 30)


def test_f2_weighs_the_article_found_twice_as_much_as_the_precision():
    missing = score_page(page(("aaaa", "article"), ("bbbb", "article")), [0])
    noisy = score_page(page(("aaaa", "article"), ("bbbb", "noise")), [0, 1])

    # Half of the article lost is worse than as much noise kept
    assert (missing.recall, missing.precision) == (0.5, 1.0)
    assert (noisy.recall, noisy.precision) == (1.0, 0.5)
    assert missing.f2 < noisy.f2


def test_noise_after_the_article_counts_too():
    assert score_page(ARTICLE, [1, 3, 4]).wrongly_kept == [4]


def test_what_the_capture_reads_twice_in_a_row_counts_once():
    # A link and the text inside it: the same text, one after the other
    linked = page(("Read", "article"), ("Donald Trump", "article"), ("Donald Trump ", "article"))

    score = score_page(linked, [0, 1])

    assert score.complete
    assert score.article_chars == len("Read") + len("Donald Trump")


def test_a_headline_the_article_shows_twice_must_be_kept_twice():
    repeated = page(("Headline", "article"), ("A paragraph.", "article"), ("Headline", "article"))

    score = score_page(repeated, [0, 1])

    assert not score.complete
    assert score.missed == [2]


def test_a_page_without_prediction_kept_nothing():
    summary = score_system("nothing", [ARTICLE], {})

    assert summary.complete == 0
    assert summary.f2 == 0.0


def test_a_page_without_article_is_complete():
    assert score_page(page(("Menu", "noise")), []).complete
