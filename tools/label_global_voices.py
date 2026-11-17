"""Labels a Global Voices capture, following docs/labelling.md: the labels of the first capture, found
by text (see first_labels.py), and for the blocks it didn't have:

- article: the headline and standfirst (above the byline), the body's text, and the quote of a tweet
  below its card (Global Voices translates it);
- optional: the text of an embedded tweet's card;
- noise: the tweet card's buttons and counts, and everything from the categories down: related
  stories, newsletter, footer. Also a block read again after a scroll.

usage: uv run python tools/label_global_voices.py ID [--show]
"""
import re
import sys

from first_labels import FirstLabels, drop_rereads, reread, texts as page_texts, write

BYLINE = re.compile(r"^(Written|Translated|Écrit|Traduit)( \(\w+\))? (by|par)\b")
END = re.compile(r"^(Categories|Catégories)$")
# An embedded tweet: its card starts at the tweet's link, and ends with its replies
TWEET_START = re.compile(r"^\d{15,}\?ref_src=twsrc")
TWEET_END = re.compile(r"^(Read \d+ repl(y|ies)|Lire \d+ réponses?|Read more on X|Voir plus sur X)$")
TWEET_UI = re.compile(r"^(Follow|Suivre|Verified account|Compte certifié|Reply|Répondre|Copy link|Copier le lien|"
                      r"Watch on X|Regarder sur X|Read video|Lire Vidéo|See more|Voir plus|"
                      r"x-for-websites-ads-info-and-privacy|[\d,.]+ ?k?|[0-9a-f]{4,5}|\S+\?format=jpg\S*|"
                      r"\d+:\d+ (AM|PM) · .*|@\w+)$")


def label_page(page: str, texts: list[str]) -> list[str]:
    known = FirstLabels(page)
    labels: list[str] = []
    last_seen: dict[str, int] = {}
    part, card = "header", False
    for i, text in enumerate(texts):
        was = known.next(text)
        if BYLINE.match(text) and part == "header":
            part = "byline"
        elif part == "byline" and was == "A":
            part = "body"
        elif END.match(text):
            part = "end"
        if TWEET_START.match(text):
            card = True

        if text in last_seen and last_seen[text] == i - 1:
            label = labels[i - 1]
        elif text in last_seen and reread(texts, i):
            label = "."
        elif was is not None:
            label = was
        elif part == "end":
            label = "."
        elif card:
            label = "." if TWEET_UI.match(text) or TWEET_START.match(text) or len(text) <= 40 else "o"
        elif part in ("header", "body"):
            label = "A"
        else:
            # Between the byline and the body: dates, sharing buttons, the main image
            label = "o"
        if card and TWEET_END.match(text):
            card = False
        labels.append(label)
        last_seen[text] = i
    drop_rereads(texts, labels)
    return labels


if __name__ == "__main__":
    page = sys.argv[1]
    texts = page_texts(page)
    write(page, texts, label_page(page, texts))
