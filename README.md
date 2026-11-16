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
  missing text. What the capture itself reads twice is not the page repeating itself: a link and the
  text inside it, or the same block on two screens that overlap while scrolling. These are removed
  before the model and the scoring, as the app does.

## Where it starts from

Measured in Universal Copy on 25 labelled pages (news in French and English, Wikipedia, recipes, docs,
Stack Overflow):

| Approach | Complete pages | F2 | Article found | Precision |
|---|---|---|---|---|
| Position rules with a perfect model | 21/25 | 0.982 | 0.982 | 0.983 |
| Position rules with Gemini Nano's real answers | 19/25 | 0.945 | 0.961 | 0.904 |

The first line is the ceiling of the rules alone: what a model that never makes a mistake would reach
through them.

These scores were measured with earlier rules, which ignored noise after the end of the article and
counted repeated text once. Step 2 measures them again with the rules above.

## Data

The 25 pages above hold the full text of copyrighted articles: they stay private, and serve only as the
final test set. The training and validation data are new captures of pages whose license allows
publishing them (Wikipedia, Creative Commons sites), labelled with the help of a large model and checked
by hand.

## Models

- **Ministral 3** (3B, then 8B), fine-tuned with LoRA: they answer like Gemini Nano does, with the
  numbers of the blocks to keep. Apache 2.0, so the weights can ship in the app.
- **A small multilingual text classifier** that scores each block: the cheapest to run on a phone.
- **Mistral Small 4** for help with labelling, and as the cloud option.

Training runs on a MacBook Pro M1 Pro with 16 GB of memory, with [MLX](https://github.com/ml-explore/mlx):
that sets the size of the models we can fine-tune.

## Plan

1. ✅ The task, the metrics and the plan (this page).
2. The dataset format, the scoring in Python, and the baselines: the position rules, and Gemini Nano's
   recorded answers.
3. Capturing and labelling the open pages.
4. Prompting Ministral 3 without fine-tuning, to measure what fine-tuning adds.
5. Fine-tuning Ministral 3 with LoRA, and training the classifier.
6. The benchmark: every approach on the private test set.
7. Exporting the best model to the phone, or serving it in the cloud.

## License

The code is under the [Apache 2.0](LICENSE) license. Each dataset keeps the license of its sources.
