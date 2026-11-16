"""The ``smart-select`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from smart_select import universal_copy
from smart_select.dataset import read_pages, read_predictions, write_pages
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

    captures = commands.add_parser("capture", help="capture a web page as Universal Copy reads it, on an emulator")
    captures.add_argument("id", help="the page's id, used for its file names")
    captures.add_argument("url")
    captures.add_argument("--license", required=True, help="the license of the page's content, like CC BY-SA 4.0")
    captures.add_argument("--out", type=Path, default=Path("data/raw"))
    captures.add_argument("--serial", help="the adb serial of the emulator, when several are connected")
    captures.add_argument("--max-swipes", type=int, default=40)

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

        for line in setup(Device(args.serial)):
            print(line)
    elif args.command == "capture":
        from smart_select.capture import Device, capture

        path = capture(Device(args.serial), args.id, args.url, args.out, {"license": args.license}, args.max_swipes)
        data = json.loads(path.read_text(encoding="utf-8"))
        end = "reached the end" if data["reachedEnd"] else f"stopped after {args.max_swipes} swipes"
        print(f"{path}: {len(data['screen'])} blocks on screen, {len(data.get('harvest') or [])} harvested, {end}")
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
