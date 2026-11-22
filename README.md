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
| 3B, 8-bit, one example | 7/40 | 0.822 | 0.816 | 0.906 | 33 s |
| 3B, 8-bit | 5/40 | 0.838 | 0.833 | 0.894 | 22 s |
| 8B, 4-bit | 1/40 | 0.840 | 0.828 | 0.930 | 46 s |
| 8B, 4-bit, one example | 1/40 | 0.826 | 0.810 | 0.941 | 68 s |

- The models find most of each article, but nearly always drop part of it: about 10 pages in each run
  miss only one or two blocks, and the title is missed on 15 to 17 pages. A larger model keeps less
  noise, not more of the article.
- One labelled example in the prompt (a Wikinews page) changes little.
- Told to answer "none" when a later window does not continue the article, the models do so on 31 of
  67 later windows: rightly on 22, which hold footers and related links, wrongly on 9, which hold part
  of the article.

Inside the app's rules, with the same answers (Universal Copy's `SmartSelectionSamplesTest`, from
`smart-select export-app-samples`). The models were not asked the app's own prompts, so both passes get
what they said about each block:

| System | Complete pages | F2 | Article found | Precision |
|---|---|---|---|---|
| Position rules alone, keeping every block they allow | 22/40 | 0.896 | 0.971 | 0.716 |
| Position rules with a perfect model | 22/40 | 0.972 | 0.970 | 0.985 |
| 3B, 8-bit, one example, in the rules | 10/40 | 0.833 | 0.824 | 0.933 |
| 3B, 8-bit, in the rules | 9/40 | 0.829 | 0.823 | 0.911 |
| 8B, 4-bit, in the rules | 1/40 | 0.840 | 0.826 | 0.938 |
| 8B, 4-bit, one example, in the rules | 1/40 | 0.833 | 0.817 | 0.946 |

- The rules add a few complete pages and some precision, not the article the models missed.
- On these pages the rules' ceiling is low: with a perfect model they complete 22 pages of 40. Code
  blocks and quotes indented in docs and Q&A, and Wikivoyage's headings, do not line up with the
  article's column. Alone, without a model, the rules complete as many pages, more than any prompted
  model.

```sh
uv sync --group models
uv run smart-select prompt --system "Ministral 3 3B, prompted" --out data/open/predictions/ministral-3b.json
```

## Fine-tuning with LoRA

Ministral 3 3B (8-bit) fine-tuned on the 103 training pages, asked exactly as above
(`src/smart_select/finetune.py`, `configs/lora-3b.yaml`):

- **Examples:** one chat per window, its answer the numbers of the window's `article` blocks. Each page
  is cut twice, as at inference and shifted by half a window: 527 training windows, 234 for validation.
- **What is learned:** only the answer, not the prompt (`mask_prompt`). LoRA adapters of rank 16 on the
  last 16 layers; the 8-bit model stays frozen.
- **Training:** 2 passes, one window per step, learning rate 1e-5 (at 1e-4 the validation loss rose
  from 0.96 to 4.55). 1,050 steps, about 17 s each: 4 h 50 on the MacBook.

| Step | 1 | 200 | 400 | 600 | 800 | 1000 | 1050 |
|---|---|---|---|---|---|---|---|
| Validation loss (10 windows) | 1.07 | 0.53 | 0.43 | 0.64 | 0.36 | 0.39 | 0.42 |

On the 40 validation pages:

| System | Complete pages | F2 | Article found | Precision | Per page |
|---|---|---|---|---|---|
| 3B, LoRA, end of training | **15/40** | **0.950** | 0.946 | 0.970 | 21 s |
| 3B, LoRA, step 800 | 9/40 | 0.929 | 0.921 | 0.977 | |
| 3B, LoRA, step 400 | 8/40 | 0.853 | 0.838 | 0.966 | |
| 3B, LoRA, end of training, in the app's rules | 15/40 | 0.934 | 0.928 | 0.966 | |
| 3B, prompted | 5/40 | 0.838 | 0.833 | 0.894 | 22 s |
| Position rules alone | 22/40 | 0.896 | 0.971 | 0.716 | |
| Position rules with a perfect model | 22/40 | 0.972 | 0.970 | 0.985 | |

- Fine-tuning triples the complete pages and lifts F2 from 0.84 to 0.95, with precision from 0.89 to
  0.97. The fine-tuned model alone has the best F2 of every system but the perfect one.
- The lowest validation loss (step 800) is not the best checkpoint: the loss counts the answer's
  tokens, and a page is complete only when no block is missed.
- Training longer does not help. Two more passes from the end of training
  (`configs/lora-3b-continued.yaml`, its validation loss measured on the same 24 windows each time)
  give 10/40 complete pages and F2 0.940 at the end, 9 to 10 pages at the checkpoints in between. The
  pages lost mostly miss one block more; on one recipe, the ingredients.
- The checkpoint was chosen on the same 40 pages it is scored on, among three: the private test set
  will give the unbiased score.
- Of the 25 pages still incomplete, 8 miss only one or two blocks: on Global Voices, the intro
  paragraph under the title; elsewhere, a section heading. The long pages of documentation and Q&A
  miss scattered blocks: code, notes, short answers.
- The app's rules no longer help: they drop article blocks the model kept, outside the column.

```sh
uv sync --group models
uv run smart-select finetune-data
uv run python tools/train_lora.py -c configs/lora-3b.yaml
uv run smart-select prompt --adapter adapters/ministral-3b --system "Ministral 3 3B, LoRA" --out data/open/predictions/ministral-3b-lora.json
```

## A per-block classifier

A small model that scores each block, article or not (`src/smart_select/classifier.py`):

- **What a block says:** its text through
  [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small), frozen: 384 numbers
  a block, close for texts of the same kind in any of its 100 languages. The validation pages hold
  Italian and Dutch, which the training pages do not.
- **Where it sits:** its edges and width, its distance from the page's column (the left edge most
  paragraphs share), its length and its place in the page.
- **Its neighbours:** a bidirectional GRU reads the page's blocks in order, so that a short line is
  judged by what is around it. 125,000 parameters on top of the encoder's 118 million.
- **Training:** optional blocks do not count in the loss. The number of epochs and the threshold are
  chosen by 5-fold cross-validation on the 103 training pages, the validation pages scored once.
  Five models with different seeds are averaged.

Embedding the 24,864 blocks of both sets takes a minute on the MacBook; training a model, seconds.

| System | Complete pages | F2 | Article found | Precision |
|---|---|---|---|---|
| **Classifier** (threshold 0.05, from cross-validation) | **29/40** | 0.955 | 0.998 | 0.828 |
| Classifier, in the app's rules | 20/40 | 0.942 | 0.972 | 0.859 |
| 3B, LoRA | 15/40 | 0.950 | 0.946 | 0.970 |
| Position rules alone | 22/40 | 0.896 | 0.971 | 0.716 |
| Position rules with a perfect model | 22/40 | 0.972 | 0.970 | 0.985 |

- The classifier completes the most pages of any system, by keeping what it is unsure of: the
  cross-validation, which puts complete pages first, chose the lowest threshold tried.
- The threshold trades complete pages for precision. On the validation pages, for illustration only
  (these were not chosen by cross-validation):

  | Threshold | 0.01 | 0.05 | 0.10 | 0.30 | 0.50 |
  |---|---|---|---|---|---|
  | Complete pages | 35/40 | 29/40 | 24/40 | 21/40 | 17/40 |
  | F2 | 0.925 | 0.955 | 0.966 | 0.970 | 0.945 |
  | Precision | 0.738 | 0.828 | 0.881 | 0.947 | 0.977 |

  At about the rules' precision, it completes 35 pages to their 22; at 0.5, it matches the fine-tuned 3B
  with a model about 30 times smaller, and no text to generate.
- The app's rules make it worse: they drop article blocks it kept, outside the column.

```sh
uv sync --group classifier
uv run smart-select classify --out data/open/predictions/classifier.json
```

## The benchmark

Every approach on the 25 private test pages, the ones the app's numbers above come from. No choice
was made on them: the classifier's two thresholds were set before (0.05 from cross-validation, 0.30
as a balanced one), and the models are the ones scored on the validation pages, trained on the same
103 pages.

| System | Complete pages | F2 | Article found | Precision |
|---|---|---|---|---|
| Position rules with a perfect model | 21/25 | 0.982 | 0.983 | 0.984 |
| **Gemini Nano in the rules (the app today)** | **19/25** | **0.917** | 0.961 | 0.840 |
| Position rules alone | 20/25 | 0.799 | 0.937 | 0.604 |
| 3B, prompted | 12/25 | 0.774 | 0.858 | 0.668 |
| 3B, prompted, in the rules | 11/25 | 0.826 | 0.874 | 0.752 |
| Classifier, threshold 0.05 | 11/25 | 0.726 | 0.923 | 0.562 |
| Classifier, threshold 0.05, in the rules | 9/25 | 0.792 | 0.874 | 0.697 |
| 3B, LoRA | 9/25 | 0.752 | 0.780 | 0.785 |
| 3B, LoRA, in the rules | 9/25 | 0.782 | 0.788 | 0.804 |
| Classifier, threshold 0.30 | 7/25 | 0.692 | 0.784 | 0.656 |

**Nothing trained here beats the app.** The validation scores did not carry over: the classifier
falls from 29/40 to 11/25, the fine-tuned 3B from 15/40 to 9/25, below the 3B without training.

The test pages are another kind of page than the training ones:

- **Commercial sites.** The open pages come from sites without ads (Wikipedia, Wikinews, Global
  Voices, Wikivoyage, MDN, Wikibooks, Stack Overflow), as their license is what allows publishing them.
  The test pages are news and recipe sites: product carousels, ad frames and their tracking links, menus
  of sections, lists of other articles. The classifier keeps them, having never seen any; on a recipe
  site it keeps 30 times more noise than article.
- **Other layouts.** A live page's summary is indented as a list: the classifier, which learned to
  trust the column, drops all of it.
- **Single screens.** Most test pages are one screen, 63 blocks for 132 in training, with less
  article in them.
- **Older captures.** Captured on a phone before the capture tool, they split more sentences around
  links: a third of their article blocks are under 20 characters, a fifth in training.

The fine-tuning made the 3B a specialist of the training pages: it lost some of what it knew of the
web at large. Gemini Nano, untrained for the task, was never specialised.

Inside the rules, the models are given the same answers for both passes; Gemini Nano was asked the
app's own prompts, the second time only about the column.

**What would fix it:** training pages from the sites people read, ads included. Their license keeps
them out of a public dataset, but not out of training: new labelled captures of commercial sites,
other than the 25 test pages, can train the models without being published, with the open pages kept
for the public results.

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
4. ✅ Prompting Ministral 3 without fine-tuning, to measure what fine-tuning adds.
5. ✅ Fine-tuning Ministral 3 with LoRA (the 3B: 15/40 complete pages, F2 0.950), and training the
   per-block classifier (29/40, F2 0.955).
6. ✅ The benchmark: every approach on the private test set. None beats the app: the training pages,
   from sites without ads, do not prepare the models for commercial sites.
7. Exporting the best model to the phone, or serving it in the cloud.

## License

The code is under the [Apache 2.0](LICENSE) license. Each dataset keeps the license of its sources.
