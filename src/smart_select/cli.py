"""The ``smart-select`` command."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from urllib.parse import urlparse

from smart_select import universal_copy
from smart_select.dataset import read_pages, read_predictions, write_pages, write_predictions
from smart_select.scoring import Summary, score_system


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="smart-select")
    commands = parser.add_subparsers(dest="command", required=True)

    imports = commands.add_parser("import-universal-copy", help="import the pages labelled in Universal Copy")
    imports.add_argument("samples", type=Path, help="the folder of captures and their predictions")
    imports.add_argument("--out", type=Path, default=Path("data/private"), help="where to write test.jsonl")
    imports.add_argument("--license", default="private", help="the license of the captured pages")

    setup = commands.add_parser("setup-device", help="prepare an emulator with Universal Copy's debug build for captures")
    setup.add_argument("--serial", help="the adb serial of the emulator, when several are connected")
    setup.add_argument("sources", type=Path, nargs="?", default=Path("data/sources.csv"),
                       help="the pages to capture: their wikis are set to expand every section")

    captures = commands.add_parser("capture", help="capture a web page as Universal Copy reads it, on an emulator")
    captures.add_argument("id", help="the page's id, used for its file names")
    captures.add_argument("url")
    captures.add_argument("--license", required=True, help="the license of the page's content, like CC BY-SA 4.0")
    captures.add_argument("--out", type=Path, default=Path("data/raw"))
    captures.add_argument("--serial", help="the adb serial of the emulator, when several are connected")
    captures.add_argument("--max-swipes", type=int, default=40)

    batch = commands.add_parser("capture-all", help="capture every page of a sources CSV not captured yet")
    batch.add_argument("sources", type=Path, nargs="?", default=Path("data/sources.csv"))
    batch.add_argument("--out", type=Path, default=Path("data/raw"))
    batch.add_argument("--serial", help="the adb serial of the emulator, when several are connected")
    batch.add_argument("--max-swipes", type=int, default=40)
    batch.add_argument("--shard", default="1/1", help="n/of: take every of-th page from the n-th, one shard an emulator")

    shows = commands.add_parser("show", help="print a captured page one block a line, to label it")
    shows.add_argument("id")
    shows.add_argument("--raw", type=Path, default=Path("data/raw"))

    builds = commands.add_parser("build-dataset", help="combine captures and labels into the training and validation sets")
    builds.add_argument("--raw", type=Path, default=Path("data/raw"))
    builds.add_argument("--labels", type=Path, default=Path("data/labels"))
    builds.add_argument("--out", type=Path, default=Path("data/open"))

    reviews = commands.add_parser("review", help="check a random sample of labelled pages by hand, in the browser")
    reviews.add_argument("--size", type=int, default=25, help="how many pages to check")
    reviews.add_argument("--seed", type=int, default=0)
    reviews.add_argument("--port", type=int, default=8765)
    reviews.add_argument("--raw", type=Path, default=Path("data/raw"))
    reviews.add_argument("--labels", type=Path, default=Path("data/labels"))
    reviews.add_argument("--sample", type=Path, default=Path("data/review-sample.json"), help="where the sample is kept")
    reviews.add_argument("--summary", action="store_true", help="only print how many blocks the reviewer changed")

    prompts = commands.add_parser("prompt", help="select with a model run on this Mac, by prompting it without training")
    prompts.add_argument("--model", default="mlx-community/Ministral-3-3B-Instruct-2512-8bit")
    prompts.add_argument("--adapter", help="a folder of LoRA weights trained on top of the model")
    prompts.add_argument("--system", required=True, help="the system's name in the predictions file")
    prompts.add_argument("--pages", type=Path, default=Path("data/open/validation.jsonl"))
    prompts.add_argument("--example", help="the id of a training page whose first window the prompt shows labelled")
    prompts.add_argument("--train", type=Path, default=Path("data/open/train.jsonl"))
    prompts.add_argument("--out", type=Path, required=True, help="the predictions file to write")

    tunes = commands.add_parser("finetune-data", help="write the training examples for fine-tuning, one chat per window")
    tunes.add_argument("--train", type=Path, default=Path("data/open/train.jsonl"))
    tunes.add_argument("--validation", type=Path, default=Path("data/open/validation.jsonl"))
    tunes.add_argument("--out", type=Path, default=Path("data/finetune"))

    classifies = commands.add_parser("classify", help="train the per-block classifier on the training pages, and select with it")
    classifies.add_argument("--system", default="Block classifier, e5-small + GRU", help="the system's name in the predictions file")
    classifies.add_argument("--train", type=Path, default=Path("data/open/train.jsonl"))
    classifies.add_argument("--pages", type=Path, default=Path("data/open/validation.jsonl"))
    classifies.add_argument("--cache", type=Path, default=Path("data/classifier/embeddings.npz"), help="where the blocks' vectors are kept")
    classifies.add_argument("--seeds", type=int, default=5, help="how many models to train and average")
    classifies.add_argument("--out", type=Path, required=True, help="the predictions file to write")

    exports = commands.add_parser("export-app-samples", help="write pages and a system's answers for Universal Copy's scoring test")
    exports.add_argument("pages", type=Path)
    exports.add_argument("predictions", type=Path)
    exports.add_argument("--out", type=Path, required=True)

    score = commands.add_parser("score", help="score systems' predictions on labelled pages")
    score.add_argument("pages", type=Path, help="a JSONL file of labelled pages")
    score.add_argument("predictions", type=Path, nargs="+", help="one predictions file per system")
    score.add_argument("--details", action="store_true", help="also print each page's score")

    args = parser.parse_args(argv)
    if args.command == "import-universal-copy":
        pages, predictions = universal_copy.import_folder(args.samples, args.out, {"license": args.license})
        write_pages(pages, args.out / "test.jsonl")
        print(f"{len(pages)} pages written to {args.out / 'test.jsonl'}, {len(predictions)} predictions files copied")
    elif args.command == "setup-device":
        from smart_select.capture import Device, setup

        with args.sources.open() as file:
            hosts = [urlparse(row["url"]).hostname or "" for row in csv.DictReader(file)]
        for line in setup(Device(args.serial), hosts):
            print(line)
    elif args.command == "show":
        from smart_select.open_dataset import show

        print(show(args.raw / f"{args.id}.json"))
    elif args.command == "build-dataset":
        from smart_select.open_dataset import build

        train, validation, unlabelled = build(args.raw, args.labels, args.out)
        print(f"{len(train)} training pages, {len(validation)} validation pages, {len(unlabelled)} captures not labelled yet")
    elif args.command == "review":
        from smart_select.review import Review, serve, summary

        if args.summary:
            print(summary(args.labels))
            return
        review = Review(args.raw, args.labels, args.sample, args.size, args.seed)
        server = serve(review, args.port)
        print(f"Reviewing {len(review.sample)} pages at http://127.0.0.1:{args.port}/  (Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n" + summary(args.labels))
    elif args.command == "capture-all":
        from smart_select.capture import Device, capture_all

        number, of = (int(part) for part in args.shard.split("/"))
        captured, failed = capture_all(Device(args.serial), args.sources, args.out, args.max_swipes, (number, of))
        print(f"{captured} pages captured, {len(failed)} failed: {' '.join(failed) or '-'}")
    elif args.command == "capture":
        from smart_select.capture import Device, capture

        path = capture(Device(args.serial), args.id, args.url, args.out, {"license": args.license}, args.max_swipes)
        data = json.loads(path.read_text(encoding="utf-8"))
        end = "reached the end" if data["reachedEnd"] else f"stopped after {args.max_swipes} swipes"
        print(f"{path}: {len(data['screen'])} blocks on screen, {len(data.get('harvest') or [])} harvested, {end}")
    elif args.command == "finetune-data":
        from smart_select.finetune import write_examples

        train = write_examples(read_pages(args.train), args.out / "train.jsonl")
        valid = write_examples(read_pages(args.validation), args.out / "valid.jsonl")
        print(f"{train} training examples, {valid} validation examples in {args.out}")
    elif args.command == "classify":
        from smart_select import classifier

        train_pages, pages = read_pages(args.train), read_pages(args.pages)
        embeddings = classifier.Embeddings(args.cache)(train_pages + pages)
        found = classifier.cross_validate(train_pages, embeddings, classifier.Settings(), args.seeds)
        print(f"Cross-validation on {len(train_pages)} training pages:")
        for epochs, threshold, complete, f2 in found.table:
            print(f"  {epochs:3} epochs: threshold {threshold:.2f}, {complete}/{len(train_pages)} complete, F2 {f2:.3f}")
        print(f"Kept: {found.epochs} epochs, threshold {found.threshold:.2f}")
        settings = classifier.Settings(epochs=found.epochs)
        averaged = classifier.ensemble(train_pages, embeddings, settings, pages, args.seeds)[found.epochs]
        predictions = classifier.kept(averaged, found.threshold)
        write_predictions(args.system, predictions, args.out)
        print(table([score_system(args.system, pages, predictions)]))
    elif args.command == "export-app-samples":
        _, kept = read_predictions(args.predictions)
        universal_copy.write_samples(read_pages(args.pages), kept, args.out)
        print(f"Samples written to {args.out}: run Universal Copy's SmartSelectionSamplesTest with -PsmartSelectSamples={args.out.resolve()}")
    elif args.command == "prompt":
        from smart_select.prompting import mlx_model, predictions, select

        pages = read_pages(args.pages)
        example = next(page for page in read_pages(args.train) if page.id == args.example) if args.example else None
        ask = mlx_model(args.model, args.adapter)
        runs = []
        log = args.out.with_suffix(".log.jsonl")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w", encoding="utf-8") as lines:
            for number, page in enumerate(pages, start=1):
                run = select(page, ask, example)
                runs.append(run)
                lines.write(json.dumps(run.__dict__, ensure_ascii=False) + "\n")
                lines.flush()
                print(f"[{number}/{len(pages)}] {page.id}: {len(run.kept)} of {len(page.blocks)} blocks kept, "
                      f"{run.windows} windows, {run.unreadable} unreadable, {run.seconds:.0f} s", flush=True)
        write_predictions(args.system, predictions(runs), args.out)
        print(table([score_system(args.system, pages, predictions(runs))]))
    else:
        pages = read_pages(args.pages)
        summaries = []
        for path in args.predictions:
            system, predictions = read_predictions(path)
            summaries.append(score_system(system, pages, predictions))
        print(table(summaries))
        if args.details:
            for summary in summaries:
                print(details(summary))


def table(summaries: list[Summary]) -> str:
    lines = [
        "| System | Complete pages | F2 | Article found | Precision |",
        "|---|---|---|---|---|",
    ]
    for summary in sorted(summaries, key=lambda summary: (summary.complete, summary.f2), reverse=True):
        lines.append(
            f"| {summary.system} | {summary.complete}/{len(summary.pages)} | {summary.f2:.3f} "
            f"| {summary.recall:.3f} | {summary.precision:.3f} |"
        )
    return "\n".join(lines)


def details(summary: Summary) -> str:
    lines = [f"\n== {summary.system}"]
    for score in summary.pages:
        mark = "  " if score.complete else "! "
        lines.append(
            f"{mark}{score.page:<22} F2 {score.f2:.2f}  article {score.article_kept:5}/{score.article_chars:5} chars"
            f"  noise kept {score.noise_kept:5} chars  missed {_ranges(score.missed)}  wrongly kept {_ranges(score.wrongly_kept)}"
        )
    return "\n".join(lines)


def _ranges(indexes: list[int]) -> str:
    ranges: list[list[int]] = []
    for index in indexes:
        if ranges and ranges[-1][1] == index - 1:
            ranges[-1][1] = index
        else:
            ranges.append([index, index])
    return ",".join(str(start) if start == end else f"{start}-{end}" for start, end in ranges) or "-"
