"""Labels a Stack Exchange capture by the page's structure, following docs/labelling.md.

Article: the question's title and body and every answer's body. Optional: votes, user cards,
"asked/edited" lines and comments. Noise: the site's header, buttons, tags, ads, sidebar, footer,
and blocks read again after a scroll.

Walks the blocks in order: a post starts at "Up vote" and its body ends at "Share"; what follows,
until the next post, is the post's user cards and comments.
usage: uv run python tools/label_stack_exchange.py ID [--show]
"""
import json
import re
import sys

ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])
page = sys.argv[1]
blocks = json.load(open(f"{ROOT}/data/raw/{page}.json"))["harvest"]

NOISE = re.compile(
    r"^(Skip to main content|Ask Question|Log in|Sign up|Search|help|stackexchange|stackoverflow|Up vote|Down vote|Save|"
    r"timeline|Share|Improve this (question|answer)|Follow|Show \d+ more comments?|Sorted by:|Highest score \(default\)|"
    r"Add a comment|Report this ad|Ad|SafeFrame Container|Copy|Run code snippet|Expand|Hide results|Edit|Accepted|"
    r"Reset to default|Trending.*|Date modified.*|Date created.*|Add a comment\s*\|.*|.*\bAds? by\b.*|"
    r"Highly active question.*|Protected question.*|Show activity on this post\.|Load \d+ more.*|"
    r"Open menu|Reply|Show all comments|Use with AI)$"
)
# The end of the answers: what follows is the sidebar and the footer
END = re.compile(r"^(Your Answer|Start asking to get answers|Not the answer you're looking for\?.*|Hot Network Questions|"
                 r"Linked|Related|Sign up or log in|Post as a guest|Required, but never shown)$")
AD = re.compile(r"Google logo Ad|googleads|doubleclick|dc_trk|14886595647878845471|Start Building with|"
                r"No charges until you activate|^clickTag$|LIBÉREZ VOS EXPÉRIENCES|Améliorez les expériences dans votre organisation|^avec un réseau autonome$|\?s=\d+&d=identicon|gravatar|user avatar|ref_src")
TAG_ROW_TOP_DELTA = 20


def label_page() -> tuple[set[int], set[int]]:
    article, optional = set(), set()
    state = "header"  # header -> title -> post -> after -> post ... -> end
    seen: dict[str, int] = {}
    in_ad = 0
    for i, block in enumerate(blocks):
        text = " ".join(block["text"].split())
        # An ad: from its logo or its id to "Report this ad"
        if re.search(r"logo Ad\b|^\d{12,}\?$", text):
            in_ad = 10
        if in_ad:
            in_ad = 0 if text == "Report this ad" else in_ad - 1
            continue
        key = text[:60]
        # Read again after a scroll: near the top of the screen, the same as a block a while ago
        repeat = len(key) >= 6 and key in seen and seen[key] < i - 3 and block["top"] < 520
        seen.setdefault(key, i)
        if END.match(text):
            state = "end"
        if state == "end" or repeat or NOISE.match(text) or AD.search(text) or text.endswith("#"):
            if text == "Up vote" and state != "end":
                state = "post"
            elif text == "Share" and state == "post":
                state = "after"
            continue
        if state == "header":
            # The title, twice: the heading and its link
            if block["left"] < 60 and block["top"] > 500 and len(text) > 15:
                article.add(i)
                state = "title"
            continue
        if state == "title":
            if text.startswith(("Asked ", "Modified ", "Viewed ")):
                optional.add(i)
            elif block["left"] < 60 and len(text) > 15:
                article.add(i)
            continue
        if state == "post" and re.match(r"^(answered|edited|asked|Commented)\b|^(Share|Follow)\b", text):
            # The post's user card: its body is over, even when the page has no "Share" button
            state = "after"
            optional.add(i)
            continue
        if state == "post":
            if re.fullmatch(r"-?\d[\d,.]*k?", text) and block["left"] < 80:
                optional.add(i)  # the vote count
            elif re.fullmatch(r"[a-z0-9.+#-]{1,35}", text) and block["left"] >= 180:
                continue  # a tag
            else:
                article.add(i)
            continue
        if state == "after":
            if re.fullmatch(r"\d+ Answers?", text):
                optional.add(i)
            else:
                optional.add(i)  # user cards, dates and comments
    return article, optional


def ranges(values: set[int]) -> str:
    out: list[list[int]] = []
    for v in sorted(values):
        if out and out[-1][1] == v - 1:
            out[-1][1] = v
        else:
            out.append([v, v])
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in out)


article, optional = label_page()
if "--show" in sys.argv:
    for i, block in enumerate(blocks):
        mark = "A" if i in article else "o" if i in optional else "."
        print(f"{mark} {i:4} {block['left']:4} {block['top']:5} {' '.join(block['text'].split())[:80]}")
else:
    if json.load(open(f"{ROOT}/data/labels/{page}.json")).get("checked_by"):
        print(page, "checked by hand, not labelled again")
        sys.exit()
    label = {"article": ranges(article), "optional": ranges(optional), "labelled_by": "Claude, by rules", "checked_by": None}
    open(f"{ROOT}/data/labels/{page}.json", "w").write(json.dumps(label) + "\n")
    print(page, len(blocks), "blocks:", len(article), "article,", len(optional), "optional")
