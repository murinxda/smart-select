from smart_select.dataset import Block, Page
from smart_select.finetune import cuts, examples


def page(labels: str) -> Page:
    """A page from one letter a block: a for article, o for optional, n for noise."""
    names = {"a": "article", "o": "optional", "n": "noise"}
    return Page(id="page", app="com.android.chrome", screen_width=1080, screen_height=2400,
                blocks=[Block(f"Block number {index}, long enough to start an article.", 42, 1000, index) for index in range(len(labels))],
                labels=[names[letter] for letter in labels])


def test_the_answer_is_the_article_blocks_of_the_window_without_the_optional_ones():
    [example] = examples(page("nnaoan"))
    assert example["messages"][-1] == {"role": "assistant", "content": "Answer: 3, 5"}
    assert example["messages"][0]["role"] == "system"


def test_a_long_page_is_also_cut_shifted_by_half_a_window():
    plain, shifted = cuts(page("a" * 150))
    assert [len(window) for window in plain] == [100, 50]
    assert [len(window) for window in shifted] == [50, 100]
    assert sum(shifted, []) == list(range(150))


def test_later_windows_say_how_the_article_starts_and_answer_none_without_article():
    chats = examples(page("a" * 100 + "n" * 30))
    later = chats[1]["messages"]
    assert "main content starts with" in later[-2]["content"]
    assert later[-1]["content"] == "Answer: none"
