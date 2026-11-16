"""A local page to check labels by hand: a person reviews a random sample of the labelled pages.

The labels of the open dataset were drafted by a model. A person checks a sample of them: for each
page, the screenshots on one side, the blocks on the other, coloured by label. A click on a block
changes its label; approving the page saves its labels with ``checked_by`` set, and the number of
blocks the person changed. Those numbers measure how far the drafts are from a person's labels.

Everything stays on the computer: the server reads the captures in ``data/raw`` and writes the
label files in ``data/labels``.
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from smart_select.universal_copy import _indexes

PAGE = Path(__file__).with_name("review.html")
SAFE_SCREENSHOT = re.compile(r"^\d+\.png$")


def ranges(indexes: set[int] | list[int]) -> str:
    """Block indexes as ranges, ``{1, 2, 3, 7}`` → ``"1-3,7"``: the format of label files."""
    out: list[list[int]] = []
    for index in sorted(set(indexes)):
        if out and out[-1][1] == index - 1:
            out[-1][1] = index
        else:
            out.append([index, index])
    return ",".join(str(start) if start == end else f"{start}-{end}" for start, end in out)


def pick_sample(labels: Path, size: int, seed: int = 0) -> list[str]:
    """A random sample of labelled pages, taken in turn from each site so that every kind of page
    is checked: ``wikipedia-en-…`` and ``wikipedia-fr-…`` are two sites."""
    by_site: dict[str, list[str]] = defaultdict(list)
    for path in sorted(labels.glob("*.json")):
        site = "-".join(path.stem.split("-")[:2])
        by_site[site].append(path.stem)
    generator = random.Random(seed)
    for pages in by_site.values():
        generator.shuffle(pages)
    sites = sorted(by_site)
    generator.shuffle(sites)
    sample: list[str] = []
    while len(sample) < size and any(by_site.values()):
        for site in sites:
            if by_site[site] and len(sample) < size:
                sample.append(by_site[site].pop())
    return sample


class Review:
    """The pages under review, and what reading and saving them means."""

    def __init__(self, raw: Path, labels: Path, sample_file: Path, size: int, seed: int) -> None:
        self.raw, self.labels = raw, labels
        # The sample is kept in a file so that it stays the same across restarts
        if sample_file.exists():
            self.sample = json.loads(sample_file.read_text(encoding="utf-8"))["pages"]
        else:
            self.sample = pick_sample(labels, size, seed)
            sample_file.write_text(json.dumps({"seed": seed, "pages": self.sample}, indent=1) + "\n", encoding="utf-8")

    def pages(self) -> list[dict]:
        out = []
        for page_id in self.sample:
            label = self._label(page_id)
            out.append({"id": page_id, "checked_by": label.get("checked_by"), "changed": label.get("review", {}).get("changed")})
        return out

    def page(self, page_id: str) -> dict:
        capture = json.loads((self.raw / f"{page_id}.json").read_text(encoding="utf-8"))
        blocks = capture.get("harvest") or capture["screen"]
        label = self._label(page_id)
        article, optional = _indexes(label.get("article", "")), _indexes(label.get("optional", ""))
        return {
            "id": page_id,
            "url": capture.get("url"),
            "license": capture.get("source", {}).get("license"),
            "reached_end": capture.get("reachedEnd"),
            "checked_by": label.get("checked_by"),
            "blocks": [
                {"text": block["text"], "left": block["left"], "top": block["top"],
                 "label": "article" if index in article else "optional" if index in optional else "noise"}
                for index, block in enumerate(blocks)
            ],
            "screenshots": sorted(path.name for path in (self.raw / page_id).glob("*.png")),
        }

    def save(self, page_id: str, labels: list[str], checked_by: str, note: str) -> dict:
        """Saves a reviewed page: its labels, who checked them, and how many blocks they changed
        from the draft."""
        before = self.page(page_id)["blocks"]
        if len(labels) != len(before) or not set(labels) <= {"article", "optional", "noise"}:
            raise ValueError("one label a block: article, optional or noise")
        label = self._label(page_id)
        draft = label.get("review", {}).get("draft") or [block["label"] for block in before]
        label.update(
            article=ranges(i for i, value in enumerate(labels) if value == "article"),
            optional=ranges(i for i, value in enumerate(labels) if value == "optional"),
            checked_by=checked_by,
        )
        changed = [i for i, (old, new) in enumerate(zip(draft, labels)) if old != new]
        # The draft is kept with the review, so that saving twice still counts from the draft
        label["review"] = {"changed": len(changed), "changed_blocks": ranges(changed), "draft": draft, "note": note}
        (self.labels / f"{page_id}.json").write_text(json.dumps(label, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"changed": len(changed)}

    def _label(self, page_id: str) -> dict:
        return json.loads((self.labels / f"{page_id}.json").read_text(encoding="utf-8"))


def serve(review: Review, port: int) -> ThreadingHTTPServer:
    sample = set(review.sample)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parts = [unquote(part) for part in self.path.split("?")[0].strip("/").split("/")]
            if parts == [""]:
                self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif parts == ["api", "pages"]:
                self._json(review.pages())
            elif len(parts) == 3 and parts[:2] == ["api", "page"] and parts[2] in sample:
                self._json(review.page(parts[2]))
            elif len(parts) == 3 and parts[0] == "screens" and parts[1] in sample and SAFE_SCREENSHOT.match(parts[2]):
                self._send((review.raw / parts[1] / parts[2]).read_bytes(), "image/png")
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parts = [unquote(part) for part in self.path.strip("/").split("/")]
            if len(parts) != 3 or parts[:2] != ["api", "page"] or parts[2] not in sample:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                self._json(review.save(parts[2], body["labels"], str(body.get("checked_by") or "reviewer"), str(body.get("note") or "")))
            except ValueError as error:
                self.send_error(HTTPStatus.BAD_REQUEST, str(error))

        def _json(self, data: object) -> None:
            self._send(json.dumps(data, ensure_ascii=False).encode(), "application/json")

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:  # quiet: one line a request is noise here
            pass

    # Only this computer can reach it
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def summary(labels: Path) -> str:
    """How many blocks the reviewer changed, over the pages checked so far."""
    reviewed = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(labels.glob("*.json"))]
    reviewed = [label for label in reviewed if label.get("checked_by")]
    if not reviewed:
        return "No page checked yet"
    blocks = sum(len(label["review"]["draft"]) for label in reviewed)
    changed = sum(label["review"]["changed"] for label in reviewed)
    untouched = sum(1 for label in reviewed if label["review"]["changed"] == 0)
    return (f"{len(reviewed)} pages checked: {untouched} without any change; "
            f"{changed} of {blocks} blocks changed ({changed / blocks:.1%})")

