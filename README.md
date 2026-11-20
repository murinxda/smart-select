# smart-select

Fine-tuning and benchmarking small models that find the main content of a phone screen.

[Universal Copy](https://play.google.com/store/apps/details?id=com.camel.corp.universalcopy) lets you copy
any text on an Android screen. It reads the screen's text through Android's accessibility service: one
block per text view or web node, with its position. On a news article, that gives the article, but also
the menus, the ads, the cookie banner and the list of other articles. **Smart select** keeps only what
you opened the screen to read.

Today smart select runs Gemini Nano on the phone, guided by position rules. This project asks whether a
small open model, fine-tuned for this one task, can do better, and small enough to run on the phone
too. If not, it can run in the cloud.

## The task

**Input:** the text blocks of a screen, in reading order, as the app reads them:

```json
{"text": "Donald Trump a estimé qu'une reprise de la guerre…", "left": 42, "right": 1034, "top": 742}
```

plus the screen's size and the app it comes from (`com.android.chrome` for instance). In harvest mode,
the person scrolls through the page and the app collects the blocks of every screen.

**Output:** the indexes of the blocks to keep.

**Labels:** each block is `article` (must be kept), `optional` (either is fine: a caption, the date…) or
`noise` (should go).

## How it is scored

Smart select removes what is not worth copying, so a selection missing a part of the article is worse
than one that keeps some noise. The scores, in order of importance:

1. **Complete pages:** the share of pages where nothing labelled `article` is missing.
2. **F2:** the harmonic mean of the article found and the precision, with the article found weighted
   twice as much. Counted in characters, not blocks.
3. **Article found** (recall) and **precision**, reported apart.

Two details follow from how the app is used:

- **All noise counts, wherever it is on the page.** Harvest mode stops where the person stops scrolling,
  but auto scroll captures the whole page, the list of other articles included. The model must work for
  both.
- **Each block counts by its own label, repeats included.** A headline the article shows twice is
  labelled `article` both times: keeping both keeps the reader's context, and dropping one counts as
  missing text. What the capture itself reads twice is not the page repeating itself:
  - the same text twice in a row, like a link and the text inside it, counts once, as the app merges
    them before anything else;
  - the same blocks on two screens that overlap while scrolling are labelled `noise` the second time:
    copying them would give the reader the same sentence twice.

## How the app selects today

Universal Copy combines Gemini Nano with **position rules**, which use where each block sits on screen:

1. **First pass:** the model reads the whole page, in batches, and says which blocks to keep.
2. **The article's column:** the left edge that lines up most of the kept text. Ads and other articles
   rarely share it: they are indented, wider, or in a side column.
3. **Second pass:** the model is asked again, only about the column, plus what belongs to it without
   lining up: the headline just before it, pieces of a sentence split by links, a slightly indented box.
4. **Repairs:** a piece of a sentence or a long paragraph the model dropped between kept lines comes
   back. What the first pass kept inside the article comes back too, but only next to kept text: an
   ad between two paragraphs stands among blocks nobody kept.

The rules have the last word: a block outside the column never reaches the selection, whatever the
model said. They exist because Gemini Nano is not trained for this task, and on its own keeps ads,
menus and lists of other articles. They are a safety net, and a net also catches some good blocks.

## Where it starts from

Measured in Universal Copy on 25 labelled pages (news in French and English, Wikipedia, recipes, docs,
Stack Overflow):

| Approach | Complete pages | F2 | Article found | Precision |
|---|---|---|---|---|
| Position rules with a perfect model | 21/25 | 0.982 | 0.983 | 0.984 |
| Position rules with Gemini Nano's real answers | 19/25 | 0.917 | 0.961 | 0.840 |
| Position rules alone, keeping every block they allow | 20/25 | 0.799 | 0.937 | 0.604 |

- The first line is the ceiling of the rules: what a model that never makes a mistake would reach
  through them. The rules miss what doesn't line up with the article: the times of a recipe in two
  columns, a list item after a cookie banner, a link placed after its sentence.
- The last line is the rules without a model: they find the article's column, but keep everything
  else in it.
- Gemini Nano completes 19 pages, but a sixth of what it keeps is noise.

These are the Universal Copy app's own selections, saved as predictions files and scored here.

## Prompting without training

Ministral 3 Instruct, run on the MacBook with MLX, prompted the way the app prompts Gemini Nano
(`src/smart_select/prompting.py`): the page cut in windows of up to 100 blocks, each block with its left
and right edges, and an answer of block numbers (`Answer: 3-7, 9`). After the first window, the prompt
says how the main content starts, as the app does. On the 40 validation pages, the model alone:

| Model | Complete pages | F2 | Article found | Precision | Per page |
|---|---|---|---|---|---|
| 3B, 8-bit, one example | 7/40 | 0.820 | 0.814 | 0.907 | 33 s |
| 3B, 8-bit | 5/40 | 0.837 | 0.831 | 0.894 | 22 s |
| 8B, 4-bit | 1/40 | 0.838 | 0.825 | 0.930 | 46 s |
| 8B, 4-bit, one example | 1/40 | 0.824 | 0.807 | 0.942 | 68 s |

- The models find most of each article, but nearly always drop part of it: about 10 pages in each run
  miss only one or two blocks, and the title is missed on 15 to 17 pages. A larger model keeps less
  noise, not more of the article.
- One labelled example in the prompt (a Wikinews page) changes little.
- Told to answer "none" when a later window does not continue the article, the models do so on 31 of
  67 later windows: rightly on 22, which hold footers and related links, wrongly on 9, which hold part
  of the article.

```sh
uv sync --group models
uv run smart-select prompt --system "Ministral 3 3B, prompted" --out data/open/predictions/ministral-3b.json
```

## Data

The 25 pages above hold the full text of copyrighted articles: they stay private, and serve only as the
final test set. The training and validation data are new captures of pages whose license allows
publishing them (Wikipedia, Creative Commons sites), labelled with the help of a large model and checked
by hand.

## Usage

```sh
uv sync
uv run pytest
uv run smart-select score <pages.jsonl> <predictions.json>... [--details]
```

**Pages** are JSONL, one page per line, with one label per block:

```json
{"id": "lighthouse", "app": "com.android.chrome", "screen_width": 1080, "screen_height": 2400,
 "blocks": [{"text": "A lighthouse is a tower…", "left": 42, "right": 1029, "top": 742}],
 "labels": ["article"], "source": {"url": "https://en.wikipedia.org/wiki/Lighthouse", "license": "CC BY-SA 4.0"}}
```

**Predictions** say which blocks a system kept on each page:

```json
{"system": "Gemini Nano", "pages": {"lighthouse": [0, 3, 4]}}
```

Any system is scored the same way, whether it runs in the app, in Python or in the cloud: it only has
to write a predictions file. `smart-select import-universal-copy <folder>` imports the pages
labelled in Universal Copy, with the predictions its scoring test writes.

**Checking labels.** The open pages' labels were drafted by Claude, following
[the labelling guide](docs/labelling.md): block by block, and by rules for the long Q&A and docs
pages. `uv run smart-select review` opens a local page to check a
random sample of them, taken from every site: the screenshots of the page on one side, its blocks
coloured by label on the other. Approving a page saves who checked it and how many blocks they
changed from the draft; `smart-select review --summary` adds those up, which says how far the drafts
can be trusted.

## Models

- **Ministral 3** (3B, then 8B), fine-tuned with LoRA: they answer like Gemini Nano does, with the
  numbers of the blocks to keep. Apache 2.0, so the weights can ship in the app.
- **A small multilingual text classifier** that scores each block: the cheapest to run on a phone.
- **Mistral Small 4** for help with labelling, and as the cloud option.

Each model is benchmarked two ways: **alone**, reading the positions of the blocks and deciding
everything, and **inside the app's rules**, as it would plug into Universal Copy today. A model trained
for the task may not need the safety net: if it does better alone, the rules can go, and with them their
ceiling.

Training runs on a MacBook Pro M1 Pro with 16 GB of memory, with [MLX](https://github.com/ml-explore/mlx):
that sets the size of the models we can fine-tune.

## Plan

1. ✅ The task, the metrics and the plan (this page).
2. ✅ The dataset format, the scoring in Python, and the baselines: the position rules, and Gemini
   Nano's recorded answers. The Python scoring gives the same results as the app's, page by page.
3. ✅ Capturing and labelling the open pages: 145 pages captured, 143 kept, 103 for training and 40 for
   validation; a sample of 25 checked by hand, and the rules fixed to match.
4. Prompting Ministral 3 without fine-tuning, to measure what fine-tuning adds: the model alone is
   measured, the model inside the app's rules is next.
5. Fine-tuning Ministral 3 with LoRA, and training the classifier.
6. The benchmark: every approach on the private test set.
7. Exporting the best model to the phone, or serving it in the cloud.

## License

The code is under the [Apache 2.0](LICENSE) license. Each dataset keeps the license of its sources.
