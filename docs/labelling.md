# Labelling guide

Each block of a page gets one label. The question is always the same: **would the person who opened
this page want this text in their copy?** Smart select is judged first on keeping all of the article,
so when in doubt between `article` and `optional`, choose `article`; between `optional` and `noise`,
choose `optional`.

| Label | Meaning | Scoring |
|---|---|---|
| `article` | What the person opened the page to read | Must be kept: missing any of it makes the page incomplete |
| `optional` | Related to the article, but either way is fine | Not counted |
| `noise` | Anything else | Counted against the selection when kept |

These rules follow the labels of the private test set, so that scores on it measure the model, not a
difference in labelling.

## Everywhere

- **Article:** the title, the body text, its headings and lists, quotes, and every piece of a sentence
  split by links or italics. Footnote marks like `[2]` inside a sentence go with the sentence.
- **Optional:** images' captions, credits and file names (`File:…`, `….jpg?utm_source=…`), the date
  and the author, a note above the article like "For other uses, see…", section headings whose text
  is folded away (mobile Wikipedia folds every section after the introduction), a summary box in the
  middle of the article (Wikipedia's infobox, a recipe's times grid when unrelated to the steps).
- **Noise:** the site's name and logo, menus, search, sign in and subscription prompts, tabs, buttons
  (edit, share, save, download), breadcrumbs, cookie banners, maintenance notices ("This article needs
  more citations"), ads, "read also" and related articles, lists of other articles, tags, comments
  sections, "last edited" lines and the footer.

## Repeats

Each block is labelled for itself, repeats included:

- A text the article really shows twice, like a headline repeated at the end, is `article` both times.
- What the capture reads twice in a row, like a link and the text inside it, gets the same label twice:
  the scoring counts it once.
- The same block read again on the next screen while scrolling is `noise` the second time: copying it
  would give the reader the same sentence twice.

## By kind of page

- **Encyclopedia (Wikipedia):** the title, the lead and every unfolded section's text, with its
  heading, are `article`. The infobox and image captions are `optional`, and so are the headings of
  folded sections. "See also", "References", "External links", "Notes" (their headings included),
  navigation boxes and categories are `noise`.
- **News (Wikinews, Global Voices):** headline, standfirst, body and subheadings are `article`; byline,
  date, captions and the "translated by" note are `optional`; sources lists, related stories, share
  buttons and newsletter prompts are `noise`.
- **Travel (Wikivoyage):** all the guide's text is `article`, listings (addresses, prices, hours)
  included: that is what a traveller copies. The map is `optional`.
- **Recipes (Wikibooks):** title, introduction, ingredients, equipment, steps and notes are `article`;
  category boxes and "this recipe needs…" notices are `noise`.
- **Docs (MDN, Android):** title, body text, code blocks, notes and tables are `article`; the table of
  contents ("In this article", "On this page"), side navigation, breadcrumbs, "Was this helpful?" and
  feedback widgets are `noise`; the "last modified" line and browser compatibility tables are
  `optional`.
- **Q&A (Stack Exchange):** the question's title and body and every answer's body are `article`;
  vote counts, user cards, "asked/edited" lines and comments are `optional`; the sidebar, hot network
  questions, related questions and the cookie banner are `noise`.
