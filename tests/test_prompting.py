from smart_select.dataset import Block, Page
from smart_select.prompting import MAX_WINDOW_BLOCKS, ranges, read_answer, select, windows


def page(*texts: str) -> Page:
    return Page(id="page", app="com.android.chrome", screen_width=1080, screen_height=2400,
                blocks=[Block(text, 42, 1000, 100 * index) for index, text in enumerate(texts)],
                labels=["noise"] * len(texts))


def test_a_long_page_is_cut_in_windows_of_consecutive_blocks():
    cut = windows([f"block {index}" for index in range(250)])
    assert [len(window) for window in cut] == [MAX_WINDOW_BLOCKS, MAX_WINDOW_BLOCKS, 50]
    assert sum(cut, []) == list(range(250))


def test_a_text_read_twice_in_a_row_is_sent_once():
    assert windows(["Link", "Link", "Text"]) == [[0, 2]]


def test_an_answer_gives_numbers_and_ranges():
    assert read_answer("Answer: 3-5, 9, 12–13", 20) == [3, 4, 5, 9, 12, 13]


def test_an_answer_reads_after_its_last_answer_word():
    assert read_answer("The menu is 1.\nAnswer: 2, 4", 5) == [2, 4]


def test_numbers_out_of_the_window_are_dropped():
    assert read_answer("Answer: 2, 8-30", 10) == [2, 8, 9, 10]


def test_none_keeps_nothing_and_a_text_without_numbers_is_unreadable():
    assert read_answer("Answer: none", 10) == []
    assert read_answer("I cannot tell.", 10) is None


def test_ranges_join_consecutive_numbers():
    assert ranges([1, 2, 3, 5, 7, 8]) == "1-3, 5, 7-8"


def test_select_maps_the_answers_back_to_the_page_and_keeps_repeats_together():
    seen = []

    def ask(messages):
        seen.append(messages[-1]["content"])
        return "Answer: 2-3"

    run = select(page("Menu", "Headline", "Headline", "A long paragraph of the article."), ask)
    assert run.kept == [1, 2, 3]
    assert run.unreadable == 0
    assert "1. (42-1000) Menu" in seen[0]
