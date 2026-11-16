import json

import pytest

from smart_select.dataset import Block, Page, read_pages, read_predictions, write_pages, write_predictions
from smart_select.universal_copy import read_capture


def test_pages_are_written_and_read_back(tmp_path):
    page = Page("p", "com.android.chrome", 1080, None, [Block("Héllo ", 0, 10, 5)], ["article"], {"license": "CC BY-SA 4.0"})

    write_pages([page], tmp_path / "pages.jsonl")

    assert read_pages(tmp_path / "pages.jsonl") == [page]


def test_each_block_needs_a_known_label():
    with pytest.raises(ValueError):
        Page("p", "app", 1080, 2400, [Block("a", 0, 1, 0)], [])
    with pytest.raises(ValueError):
        Page("p", "app", 1080, 2400, [Block("a", 0, 1, 0)], ["headline"])


def test_predictions_are_written_and_read_back(tmp_path):
    write_predictions("rules", {"p": [3, 1]}, tmp_path / "rules.json")

    assert read_predictions(tmp_path / "rules.json") == ("rules", {"p": [1, 3]})


def test_a_universal_copy_capture_becomes_a_page(tmp_path):
    capture = {
        "package": "com.android.chrome",
        "screenWidth": 1080,
        "screen": [{"text": "screen only", "top": 0, "left": 0, "right": 10}],
        "harvest": [{"text": f"block {index}", "top": index, "left": 0, "right": 10} for index in range(6)],
        "labels": {"article": "1-3,5", "optional": "4"},
    }
    (tmp_path / "news.json").write_text(json.dumps(capture))

    page = read_capture(tmp_path / "news.json", {"license": "private"})

    # The harvest holds every screen of the page: it wins over the last screen
    assert [block.text for block in page.blocks] == [f"block {index}" for index in range(6)]
    assert page.labels == ["noise", "article", "article", "article", "optional", "article"]
    assert page.screen_height is None


def test_a_capture_without_labels_is_skipped(tmp_path):
    (tmp_path / "raw.json").write_text(json.dumps({"package": "app", "screenWidth": 1080, "screen": []}))

    assert read_capture(tmp_path / "raw.json", {}) is None
