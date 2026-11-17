"""Labels an MDN or Android Developers capture by the page's structure, following docs/labelling.md.

Article: the title, the body text, headings, code and tables. Optional: browser support summaries,
the specifications and compatibility tables, figure names and captions, "last modified" lines.
Noise: the site's header and navigation, the table of contents, buttons (copy, play, run), code
language labels, ads, cookie banners, feedback widgets, "See also" and related links, the footer,
and blocks read again after a scroll.
usage: uv run python tools/label_docs.py ID [--show]
"""
import json
import re
import sys

ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])
page = sys.argv[1]
blocks = json.load(open(f"{ROOT}/data/raw/{page}.json"))["harvest"]
texts = [" ".join(b["text"].split()) for b in blocks]

BUTTON = re.compile(
    r"^(Copy|Copier|Play|Run|Reset|Reset example, and clear console output|AD|PUBLICITÉ|Toggle sidebar|"
    r"Basculer la barre latérale|Run example in MDN Playground.*|Exécuter l'exemple.*|JS|HTML|CSS|JSON|HTTP|BASH|SH|"
    r"APACHECONF|NGINX|PLAIN|Kotlin|Java|Groovy|Kotlin build\.gradle\.kts|Groovy build\.gradle|Views|Compose|"
    r"Dark code theme|Action buttons|Copy code sample|content_copy|Copy link to this section.*|.*Copy link to this section:.*|"
    r"Learn more|Understood|Lower header breadcrumb|X|Helpful|Not helpful|Was this helpful\?|thumb_up|thumb_down|"
    r"Bookmark collections drop down|Open dropdown|LLM Tools|Copy page as markdown|More LLM Tools options|"
    r"arrow_drop_down|expand_more|more_horiz|Use with AI|Report a problem with this content.*|View this page on GitHub.*|"
    r"No recommendations at this time\.|Try signing in to your Google account\.|"
    r"Don't want to see ads\?|Vous ne voulez pas voir de publicités \?|View in English|Always switch to English|"
    r"Cette page a été traduite.*|This page was translated.*)$"
)
AD = re.compile(r"aHR0c|Otari|Cloudflare Build|MongoDB|Discover Otari|Get started$|Build for the agent era|"
                r"Deploy serverless functions|Paragon|Customer file sync|^How it works$|^English \(US\)$|^Français$|^Web$|uses cookies from Google|Control Your LLM Infrastructure|Meet Otari")
# The table of contents, then the body starts at its first heading
TOC = re.compile(r"^(In this article|Dans cet article|On this page)$")
# Sections after the body: optional ones, then noise
OPTIONAL_SECTIONS = re.compile(r"^(Specifications|Spécifications|Browser compatibility|Compatibilité des navigateurs)$")
NOISE_SECTIONS = re.compile(r"^(See also|Voir aussi|Help improve MDN|Aider à améliorer MDN|Aidez à améliorer MDN|"
                            r"Additional resources|Next steps|Recommended for you|Content and code samples on this page.*|"
                            r"Related content|Samples|Videos|Blogs)$")
OPTIONAL_LINE = re.compile(r"^(Baseline .*|This page was last modified on .*|Last updated .*|Figure \d+\..*|"
                           r"Console output|Sortie de la console|.*\.(png|jpg|svg|gif)(\?.*)?$|[a-z0-9]+[_-][a-z0-9_-]+$|[a-z]+\d+$)")


def label_page() -> tuple[set[int], set[int]]:
    article, optional = set(), set()
    # The title: the first big text block at the left margin, below the header
    title = next(i for i, b in enumerate(blocks) if b["left"] < 60 and 480 <= b["top"] <= 1000
                 and len(texts[i]) > 3 and not BUTTON.match(texts[i]) and not texts[i].startswith(("Web", "Android")))
    toc_start = next((i for i in range(title, len(blocks)) if TOC.match(texts[i])), None)
    # The table of contents lists the headings, each once or twice, in a narrow column, before the body's
    # first heading at the left margin again
    body_start = title + 1
    if toc_start is not None:
        # The body starts at the first block at the left margin after the table of contents, whose
        # entries are indented: the introduction on Android, the first heading on MDN
        body_start = next((i for i in range(toc_start + 1, len(blocks))
                           if blocks[i]["left"] == 42 and not BUTTON.match(texts[i]) and not AD.search(texts[i])
                           and not TOC.match(texts[i])), toc_start + 1)
    state = "article"
    seen: dict[str, int] = {}
    for i in range(title, len(blocks)):
        text = texts[i]
        key = text[:40]
        # Read again after a scroll: the same text, higher on the screen than when first read
        repeat = len(key) >= 6 and key in seen and blocks[i]["top"] < blocks[seen[key]]["top"] - 100
        seen.setdefault(key, i)
        if NOISE_SECTIONS.match(text) and i > body_start and blocks[i]["left"] <= 42:
            state = "noise"
        elif OPTIONAL_SECTIONS.match(text) and i > body_start and state == "article" and blocks[i]["left"] <= 42:
            state = "optional"
        breadcrumb = text.isupper() and len(text) < 40
        if state == "noise" or repeat or breadcrumb or BUTTON.match(text) or AD.search(text):
            continue
        if i == title:
            article.add(i)
        elif toc_start is not None and toc_start <= i < body_start:
            continue
        elif state == "optional" or OPTIONAL_LINE.match(text):
            optional.add(i)
        else:
            article.add(i)
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
        print(f"{mark} {i:4} {block['left']:4} {block['top']:5} {texts[i][:80]}")
else:
    label = {"article": ranges(article), "optional": ranges(optional), "labelled_by": "Claude, by rules", "checked_by": None}
    open(f"{ROOT}/data/labels/{page}.json", "w").write(json.dumps(label) + "\n")
    print(page, len(blocks), "blocks:", len(article), "article,", len(optional), "optional")
