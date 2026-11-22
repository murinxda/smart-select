import pytest

from smart_select.classifier import Settings, counted, kept, position_features, targets
from smart_select.dataset import Block, Page

PARAGRAPH = "A paragraph of the article, long enough to say where the article's column is on the screen."


def page(blocks: list[tuple[str, int, int, str]], id: str = "page") -> Page:
    """A page from (text, left, right, label) blocks."""
    return Page(id=id, app="com.android.chrome", screen_width=1000, screen_height=2400,
                blocks=[Block(text, left, right, index) for index, (text, left, right, _) in enumerate(blocks)],
                labels=[label for *_, label in blocks])


def test_the_column_is_the_left_edge_most_paragraphs_share():
    features = position_features(page([("Menu", 900, 990, "noise"), (PARAGRAPH, 40, 960, "article"),
                                       (PARAGRAPH + " Again.", 42, 960, "article"), ("Side box text " * 8, 600, 990, "noise")]))
    assert [round(row[3], 2) for row in features] == [0.86, 0.0, 0.0, 0.56]
    assert [row[4] for row in features] == [0.0, 1.0, 1.0, 0.0]


def test_a_text_read_twice_in_a_row_is_read_once_and_gets_the_first_reading_s_answer():
    repeated = page([("Title", 40, 960, "article"), ("Title", 40, 960, "article"), (PARAGRAPH, 40, 960, "article")])
    assert counted(repeated) == [0, 2]
    assert len(position_features(repeated)) == 2


def test_optional_blocks_do_not_count_in_the_loss():
    values, counts = targets(page([("Title", 40, 960, "article"), ("Date", 40, 300, "optional"), ("Ad", 40, 960, "noise")]))
    assert values == [1.0, 0.0, 0.0]
    assert counts == [1.0, 0.0, 1.0]


def test_the_blocks_kept_are_those_scored_at_the_threshold_or_above():
    assert kept({"page": [0.1, 0.3, 0.29, 0.9]}, 0.3) == {"page": [1, 3]}


def test_the_page_model_learns_to_tell_the_column_from_the_side():
    torch = pytest.importorskip("torch")
    from smart_select.classifier import scores, train

    pages = [page([(PARAGRAPH, 40, 960, "article"), ("Sponsored link " * 6, 600, 990, "noise"),
                   (PARAGRAPH, 40, 960, "article"), ("Read also " * 9, 600, 990, "noise")], id=f"p{n}") for n in range(4)]
    # Same text vectors for every block: only the positions can tell them apart
    embeddings = {p.id: torch.ones(len(counted(p)), 8).numpy() for p in pages}
    model = train(pages, embeddings, Settings(hidden=8, dropout=0.0, learning_rate=1e-2, epochs=60))[60]
    found = scores(model, pages[:1], embeddings)["p0"]
    assert found[0] > 0.8 and found[2] > 0.8
    assert found[1] < 0.2 and found[3] < 0.2


def test_a_second_reading_gets_the_score_of_the_first():
    torch = pytest.importorskip("torch")
    from smart_select.classifier import scores, train

    repeated = page([("Title", 40, 960, "article"), ("Title", 40, 960, "article"), ("Ad " * 30, 600, 990, "noise")])
    embeddings = {"page": torch.zeros(2, 4).numpy()}
    model = train([repeated], embeddings, Settings(hidden=4, epochs=1))[1]
    first, second, _ = scores(model, [repeated], embeddings)["page"]
    assert first == second
