import json

from smart_select.review import Review, pick_sample, ranges, summary


def write_capture(raw, page_id, texts):
    blocks = [{"text": text, "left": 42, "right": 1000, "top": 100 * i} for i, text in enumerate(texts)]
    (raw / f"{page_id}.json").write_text(json.dumps({"package": "com.android.chrome", "screenWidth": 1080, "harvest": blocks}))


def write_label(labels, page_id, article, optional=""):
    (labels / f"{page_id}.json").write_text(json.dumps(
        {"article": article, "optional": optional, "labelled_by": "Claude", "checked_by": None}))


def test_indexes_become_ranges():
    assert ranges({7, 1, 2, 3}) == "1-3,7"
    assert ranges([]) == ""


def test_the_sample_takes_pages_from_every_site(tmp_path):
    for page_id in ["wikipedia-en-a", "wikipedia-en-b", "wikipedia-en-c", "wikipedia-fr-a", "mdn-en-a"]:
        write_label(tmp_path, page_id, "0")

    sample = pick_sample(tmp_path, 3, seed=1)

    assert sorted(page.split("-")[1] for page in sample if page.startswith("wikipedia")) == ["en", "fr"]
    assert "mdn-en-a" in sample
    assert pick_sample(tmp_path, 3, seed=1) == sample


def test_a_review_saves_labels_and_counts_changes_from_the_draft(tmp_path):
    raw, labels = tmp_path / "raw", tmp_path / "labels"
    raw.mkdir(), labels.mkdir()
    write_capture(raw, "wikipedia-en-a", ["Menu", "Title", "Body", "Caption"])
    write_label(labels, "wikipedia-en-a", "1-2", "3")
    review = Review(raw, labels, tmp_path / "sample.json", 1, 0)

    assert [block["label"] for block in review.page("wikipedia-en-a")["blocks"]] == ["noise", "article", "article", "optional"]
    assert review.save("wikipedia-en-a", ["noise", "article", "article", "article"], "LA", "") == {"changed": 1}
    # Saving again still counts from Claude's draft, not from the first review
    assert review.save("wikipedia-en-a", ["noise", "article", "article", "noise"], "LA", "") == {"changed": 1}

    saved = json.loads((labels / "wikipedia-en-a.json").read_text())
    assert (saved["article"], saved["optional"], saved["checked_by"]) == ("1-2", "", "LA")
    assert saved["labelled_by"] == "Claude"
    assert summary(labels) == "1 pages checked: 0 without any change; 1 of 4 blocks changed (25.0%)"


def test_the_sample_stays_the_same_across_restarts(tmp_path):
    raw, labels = tmp_path / "raw", tmp_path / "labels"
    raw.mkdir(), labels.mkdir()
    for page_id in ["wikipedia-en-a", "mdn-en-a"]:
        write_label(labels, page_id, "0")
    first = Review(raw, labels, tmp_path / "sample.json", 1, 0).sample

    write_label(labels, "android-en-a", "0")

    assert Review(raw, labels, tmp_path / "sample.json", 1, 5).sample == first
