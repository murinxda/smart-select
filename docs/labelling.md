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
  and the author, a note above the article like "For other uses, see…", a summary box in the
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

- **Encyclopedia (Wikipedia):** the title, the lead and every section's text, with its heading, are
  `article` (the captures unfold every section: `setup-device` turns on "Expand all sections" on each
  Wikimedia site). The infobox and image captions are `optional`. "See also", "References", "External links", "Notes" (their headings included),
  navigation boxes and categories are `noise`.
- **Tables in wiki pages** (Wikipedia, Wikivoyage, Wikibooks: results, cabinets, track lists, a
  recipe's ingredients grid) are `optional`: their cells come out as short blocks that are hard to
  copy as text. The title and the headings around them stay `article`. Docs tables stay `article`.
- **News (Wikinews, Global Voices):** headline, standfirst, body and subheadings are `article`; byline,
  date, captions and the "translated by" note are `optional`; sources lists, related stories, share
  buttons and newsletter prompts are `noise`.
- **Travel (Wikivoyage):** all the guide's text is `article`, listings (addresses, prices, hours)
  included: that is what a traveller copies. The map is `optional`; its credits ("Wikimedia maps |
  Map data ©…") and scale ("500 m"), the guide's status notice ("This city travel guide to … is an
  outline"), the list of the region's other articles, "Créez la catégorie…" and calls to contribute are `noise`.
- **Recipes (Wikibooks):** title, introduction, ingredients, equipment, steps and notes are `article`;
  category boxes and "this recipe needs…" notices are `noise`.
- **Docs (MDN, Android):** title, body text, code blocks, notes and tables are `article`; the table of
  contents ("In this article", "On this page"), side navigation, breadcrumbs, "Was this helpful?" and
  feedback widgets, and embedded videos' cards (player, channel, title) are `noise`; the "last modified" line and browser compatibility tables are
  `optional`, and so are code samples' file names ("IndexSnippets.kt").
- **Q&A (Stack Exchange):** the question's title and body and every answer's body are `article`;
  vote counts, user cards, "asked/edited" lines and comments are `optional`; the sidebar, hot network
  questions, related questions and the cookie banner are `noise`.

## Commercial sites (private training pages)

News, tech and recipe sites that live on ads, captured in Chrome with their cookie wall accepted. The
rules above still apply; these pages add:

- **Ads and sponsored content are `noise`**, wherever they are: "Advertisement", "Sponsor Message",
  "Annonce", ad networks' links and file names (`googleads…`, `trc.taboola.com/…`, `amt?ias_…`), product
  carousels and shopping cards ("Available at Amazon", prices, "Buy now"), sponsored links and "You may
  like" grids (Taboola, Outbrain), and the text of an ad inside the article.
- **Subscription, donation and app prompts are `noise`:** "Subscribe", offers and prices of a
  subscription, "This free press is powered by you… Donate", "Read in the app", "Add … on Google",
  newsletter sign-up boxes and push-notification prompts.
- **Consent banners are `noise`**, with all their text, when the capture still holds one.
- **Audio and video players are `noise`:** "Listen to this article", "36-Minute Listen", play, mute,
  full screen, a live stream bar ("On Air Now").
- **"Read also" links inside the body are `noise`**, like related articles after it; so are the
  comment count, comments, and readers' reviews of a recipe.
- **A live page's posts** (time and text) follow the test set: the key facts box and the posts are
  `optional`, the posts' times too.
- **Recipes:** title, introduction, ingredients, equipment, steps and the author's tips are `article`;
  the rating, number of reviews, times, difficulty, cost, servings and nutrition facts are `optional`;
  readers' reviews and photos, "Jump to recipe", "Print" and "Save" buttons are `noise`.
- **The section label above the headline is `noise`** ("POLITICS", "EXCLUSIVE", "ANALYSIS", a site's
  tagline above its title), as in the test set.
- **Embedded posts** (X, Instagram, TikTok): the post's text is `optional`, as on Global Voices; the
  account, buttons, counts and the embed's own cookie prompts are `noise`.
- **The author's box after the article** is `optional`, like the byline. A recipe's or an article's
  "Frequently asked questions", written by the site in the article's column, is `article`.
- **A page that loads the next article below** (infinite scroll): everything from the next article
  on is `noise`.
- **Reviews (tech):** the verdict, score, pros and cons are `article`: they are part of the review.
  Product cards with prices and "Buy" links are `noise`.

## Labelled by rules

Q&A and docs pages run to 300 to 800 blocks, with the same structure on every page of a site. Their
drafts were written by rules that follow this guide, `tools/label_stack_exchange.py` and
`tools/label_docs.py`, checked against labels by hand on a few pages, and spot-checked on each page
(`--show` prints each block with its label).

The other pages were first captured with Wikimedia's sections folded, and labelled block by block
(commit a097f5d). Captured again with their sections unfolded, they keep those labels for the blocks
they had before, found by their text (`tools/first_labels.py`), and rules label the rest:
`tools/label_wikis.py` by the section a block is in (its heading follows an edit link; "References",
"See also" and their translations start the noise), `tools/label_global_voices.py` by the part of the
page (headline, body, embedded posts, what follows the categories). Both mark as `noise` a text read
again after a scroll, even in another form: a paragraph cut at another line as it crosses the edge of
the screen, when 90% of its runs of 6 words are in the article before it.

Tables are found by their shape: a run of narrow blocks, some of them side by side on a row
(`table_cells` in `tools/label_wikis.py`).

All label files say `"labelled_by": "Claude, by rules"`.

## Checked by hand

A sample of 25 pages from every site was checked in `smart-select review`: 1016 of their 3779 blocks
changed (27%), 821 of them tables made `optional`. The rules were then fixed to follow those labels and
run again on the other 120 pages; on the 25 checked pages they now differ from the hand labels on 84
blocks, mostly choices made for one page. The rules never overwrite a page someone checked
(`"checked_by"` set).

Two pages are left out of the dataset (`EXCLUDED` in `src/smart_select/open_dataset.py`): Universal
Copy reads their math formulas one symbol a block, out of order.
