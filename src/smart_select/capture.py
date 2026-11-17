"""Captures a web page the way Universal Copy reads it, on an Android emulator.

The capture drives the real app, so the blocks are exactly what smart select will get: a debug build
of Universal Copy saves each screen it reads, and in harvest mode the blocks of every screen the page
scrolls through. Needs:

- an emulator (or a phone) reachable with ``adb``, with Chrome;
- a debug build of Universal Copy installed, its accessibility service on.

The page is opened in Chrome, cookie walls are accepted and popups dismissed, then copy mode starts
and scrolls to the end of the page, like auto scroll does. A screenshot of each screen is saved next
to the capture, to check the labels against what the page looks like.

Speed matters: a page has 10 to 40 screens, and the dataset hundreds of pages. What costs time is
``adb``: a ``uiautomator`` dump takes about 2 s, and sending a screenshot to the computer about 1 s.
So the screen is compared on the device, by a hash of its pixels (0.2 s), screenshots are saved on
the device as JPEG (0.2 s) and fetched once at the end, and waits stop as soon as the screen stops
moving rather than after a fixed time. Several emulators can split the pages between them
(``capture-all --serial … --shard 1/2``).
"""

from __future__ import annotations

import csv
import html
import json
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

APP = "com.camel.corp.universalcopy"
DEVICE_DIR = f"/sdcard/Android/data/{APP}/files/smart-select"
# Screenshots are written here on the device, then fetched at the end of each page
SCREENS_DIR = "/data/local/tmp/smart-select-screens"

# Accepting cookies avoids "subscribe or accept" walls that hide the article. Notifications, sign-in
# and app banners are refused.
ACCEPT = [
    "Accepter", "Accepter et continuer", "Accept all", "Tout accepter", "J'accepte", "Accept", "Aceptar",
    "Accept and continue", "I agree", "Agree", "Agree and close", "ACCEPT AND CONTINUE", "Accepter & Fermer",
    "I Accept All", "Yes, I agree", "ACCEPTER LES COOKIES", "Accepter tout", "Tout accepter et continuer",
    "Alle akzeptieren", "Aceptar todo", "Aceitar",
]
ACCEPT_PREFIXES = ("j'accepte", "accept ", "tout accepter", "i accept", "agree")
DISMISS = ["No thanks", "Not now", "No, thanks", "Close", "Fermer", "Use without an account", "Stay signed out"]
# Sites without cookie walls or popups: one check is enough
QUIET_SITES = ("wikipedia.org", "wikivoyage.org", "wikinews.org", "wikibooks.org")

# In pixels, the height of the navigation bar at the bottom of a 1080 x 2400 screen
NAVIGATION_BAR = 150
# In pixels, harvest mode's stop button on a 1080 x 2400 screen
STOP_BUTTON = (920, 170, 1020, 270)
# Where the page starts below harvest mode's bar
HARVEST_BAR_BOTTOM = 300
# The height of the bands compared to tell a page that scrolls from a map that pans: a map would
# need to be taller than the screen less two bands to cover both
BAND = 400
# Where drags start, (x, y): the left of the text column first, then the middle and the right side
# when the page does not move, then the same higher on the screen. Not the middle first: a map in an
# infobox, on the right half, pans under the drag instead of the page, and the screen changing looks
# like the page scrolling. Not only one height: an ad or a code block as wide as the screen takes
# every drag that starts on it
SWIPE_STARTS = ((150, 1900), (540, 1900), (990, 1900), (150, 1300), (540, 1300), (150, 2200))


@dataclass(frozen=True)
class Node:
    text: str
    description: str
    bounds: tuple[int, int, int, int]

    @property
    def label(self) -> str:
        return self.text or self.description


@dataclass
class Timer:
    """How long each step of a capture took, to see where the time goes."""

    steps: dict[str, float] = field(default_factory=dict)
    start: float = field(default_factory=time.monotonic)

    def lap(self, step: str) -> None:
        now = time.monotonic()
        self.steps[step] = self.steps.get(step, 0) + now - self.start
        self.start = now

    def __str__(self) -> str:
        return " ".join(f"{step} {seconds:.0f}s" for step, seconds in self.steps.items()) + f", total {sum(self.steps.values()):.0f}s"


class Device:
    def __init__(self, serial: str | None = None) -> None:
        self.adb = ["adb"] + (["-s", serial] if serial else [])
        self._screen: tuple[int, int, int] | None = None

    def shell(self, *command: str, binary: bool = False, raw: str | None = None) -> str | bytes:
        """Runs a command on the device; ``raw`` is a shell line run as it is, pipes included."""
        # The device's shell reads one command line: a URL's "&" must not end it
        line = raw if raw is not None else " ".join(shlex.quote(part) for part in command)
        try:
            result = subprocess.run(self.adb + ["exec-out", line], capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            return b"" if binary else ""
        return result.stdout if binary else result.stdout.decode(errors="ignore")

    def nodes(self) -> list[Node]:
        dump = self.shell("uiautomator", "dump", "/dev/tty")
        nodes = []
        for match in re.finditer(r"<node [^>]*>", dump):
            def attribute(name: str, node: str = match.group(0)) -> str:
                found = re.search(rf' {name}="([^"]*)', node)
                return html.unescape(found.group(1)).strip() if found else ""

            bounds = tuple(map(int, re.findall(r"\d+", attribute("bounds")))) or (0, 0, 0, 0)
            nodes.append(Node(attribute("text"), attribute("content-desc"), bounds))
        return nodes

    def tap(self, bounds: tuple[int, int, int, int]) -> None:
        self.shell("input", "tap", str((bounds[0] + bounds[2]) // 2), str((bounds[1] + bounds[3]) // 2))

    def swipe_up(self, x: int = 540, y: int = 1900) -> None:
        """Drags the page up by up to 1,400 pixels, about two thirds of the page's height on screen,
        from (x, y) and no higher than the toolbar.

        A drag, not a swipe: the finger stops before it lifts, so the page does not fling on. It
        stops sooner, and always moves by the same distance, which keeps an overlap between screens."""
        end = max(y - 1400, 400)
        steps = [y - (y - end) * k // 4 for k in range(1, 5)] + [end]
        moves = "; ".join(f"input motionevent MOVE {x} {step}" for step in steps)
        self.shell(raw=f"input motionevent DOWN {x} {y}; {moves}; sleep 0.15; input motionevent UP {x} {end}")

    def page_hash(self) -> tuple[str, str]:
        """Hashes of a band at the top and one at the bottom of the page on screen, below harvest
        mode's bar and above the navigation bar, computed on the device.

        Not the bar: harvest mode's counter keeps changing there. Two bands far apart: a map or a
        carousel under the finger pans in one of them at most, a page that scrolls moves both."""
        width, height, header = self.screen()

        def band(top: int, bottom: int) -> str:
            start, length = header + top * width * 4, (bottom - top) * width * 4
            return self.shell(raw=f"screencap | tail -c +{start + 1} | head -c {length} | md5sum").split(" ")[0]

        bottom = height - NAVIGATION_BAR
        return band(HARVEST_BAR_BOTTOM, HARVEST_BAR_BOTTOM + BAND), band(bottom - BAND, bottom)

    def screen(self) -> tuple[int, int, int]:
        """The screen's width and height in pixels, and the size of a raw screenshot's header."""
        if self._screen is None:
            head = self.shell(raw="screencap | head -c 16", binary=True)
            width, height = int.from_bytes(head[0:4], "little"), int.from_bytes(head[4:8], "little")
            # 4 bytes a pixel, after a header of 12 or 16 bytes depending on the Android version
            size = int(self.shell(raw="screencap | wc -c").strip())
            self._screen = (width, height, size - width * height * 4)
        return self._screen

    def save_screenshot(self, name: str) -> None:
        """Saves a JPEG screenshot on the device, where it is quick to write: see ``fetch_screenshots``."""
        self.shell(raw=f"mkdir -p {SCREENS_DIR} && screencap -j {SCREENS_DIR}/{name}")

    def fetch_screenshots(self, folder: Path) -> None:
        subprocess.run(self.adb + ["pull", f"{SCREENS_DIR}/.", str(folder)], capture_output=True, timeout=300)
        self.shell(raw=f"rm -rf {SCREENS_DIR}")

    def focus(self) -> str:
        return self.shell(raw="dumpsys window | grep mCurrentFocus").partition("mCurrentFocus")[2].strip()

    def files(self) -> set[str]:
        return set(self.shell("ls", DEVICE_DIR).split())


def capture_all(device: Device, sources: Path, out: Path, max_swipes: int = 40, shard: tuple[int, int] = (1, 1)) -> tuple[int, list[str]]:
    """Captures every page of a sources CSV (id, url, license…) not captured yet in ``out``.

    ``shard`` (n, of) takes every ``of``-th page starting at the n-th, so that several emulators can
    split the pages. A page that fails is logged and skipped: the next run tries it again. Returns
    how many pages were captured, and the ids of those that failed.
    """
    with sources.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    number, of = shard
    captured, failed = 0, []
    for index, row in enumerate(rows):
        if index % of != number - 1 or (out / f"{row['id']}.json").exists():
            continue
        print(f"[{index + 1}/{len(rows)}] {row['id']}", flush=True)
        try:
            source = {key: row[key] for key in ("license", "source", "category", "language")}
            timer = Timer()
            path = capture(device, row["id"], row["url"], out, source, max_swipes, timer)
            data = json.loads(path.read_text(encoding="utf-8"))
            end = "end" if data["reachedEnd"] else "cut"
            print(f"  {len(data.get('harvest') or [])} blocks, {data['screens']} screens, {end}; {timer}", flush=True)
            captured += 1
        except Exception as error:  # one page must not stop the others
            print(f"  failed: {error}", flush=True)
            failed.append(row["id"])
        finally:
            leave(device)
    return captured, failed


def leave(device: Device) -> None:
    """Back to the home screen, closing copy mode if it is still open."""
    for _ in range(3):
        if "CopyActivity" not in device.focus():
            break
        device.shell("input", "keyevent", "KEYCODE_BACK")
        time.sleep(0.5)
    device.shell("input", "keyevent", "KEYCODE_HOME")
    time.sleep(0.5)


# Wikimedia's sites on a phone show each section of an article folded under its heading, until it is
# tapped: a capture would only hold the introduction and the headings
MEDIAWIKI_HOSTS = re.compile(r"\.(wikipedia|wikinews|wikivoyage|wikibooks)\.org$")
# The switch's id doesn't follow its state: its "checked" attribute does
EXPAND_SECTIONS = r"skin-client-pref-mf-expand-sections-value-[01]"


def expand_wiki_sections(device: Device, host: str) -> bool:
    """Turns on "Expand all sections" in a Wikimedia site's settings, kept by Chrome for that site:
    returns whether it is on."""
    def switch() -> tuple[tuple[int, int, int, int], bool] | None:
        """The switch's bounds and state, when it is on screen."""
        found = re.search(rf'<node [^>]*resource-id="{EXPAND_SECTIONS}"[^>]*>', device.shell("uiautomator", "dump", "/dev/tty"))
        if not found:
            return None
        bounds = tuple(map(int, re.findall(r"\d+", re.search(r'bounds="([^"]*)"', found.group(0)).group(1))))
        # Below the screen, Chrome gives it a box of no height at the screen's bottom edge
        return (bounds, 'checked="true"' in found.group(0)) if bounds[3] > bounds[1] else None

    device.shell("am", "start", "-a", "android.intent.action.VIEW", "-d", f"https://{host}/wiki/Special:MobileOptions",
                 "-e", "com.android.browser.application_id", "smart-select", "com.android.chrome")
    wait_for_text(device, enough=5)
    # A banner can push the settings below the screen
    for _ in range(3):
        if wait_until(lambda: switch() is not None, timeout=5, interval=0.5):
            break
        device.swipe_up(150)
        settle(device)
    # The page shows the switch off until its script reads the saved setting: tapping it then would
    # turn a saved setting off
    time.sleep(2)
    found = switch()
    if found is None:
        return False
    bounds, on = found
    if not on:
        device.tap(bounds)
    return wait_until(lambda: (switch() or (None, False))[1], timeout=10, interval=0.5)


def setup(device: Device, hosts: Iterable[str] = ()) -> list[str]:
    """Prepares a device for captures, once: returns what it did. ``hosts`` are the sites of the
    pages to capture."""
    done = []
    # Chrome reads extra flags from this file when it is the debug app: no first-run screens
    device.shell("sh", "-c", "echo '_ --disable-fre --no-default-browser-check --no-first-run' > /data/local/tmp/chrome-command-line")
    device.shell("am", "set-debug-app", "--persistent", "com.android.chrome")
    device.shell("am", "force-stop", "com.android.chrome")
    done.append("Chrome starts without its first-run screens")
    service = f"{APP}/{APP}.UniversalCopyService"
    device.shell("settings", "put", "secure", "enabled_accessibility_services", service)
    device.shell("settings", "put", "secure", "accessibility_enabled", "1")
    done.append("Universal Copy's accessibility service is on")
    device.shell("appops", "set", APP, "SYSTEM_ALERT_WINDOW", "allow")
    done.append("Universal Copy may draw over other apps, which harvest mode needs")
    # Without animations, screens settle sooner, and a still screen means the page has stopped
    for setting in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        device.shell("settings", "put", "global", setting, "0")
    done.append("Animations are off")
    for host in sorted({host for host in hosts if MEDIAWIKI_HOSTS.search(host)}):
        # Once more if it failed: a tap while the page still moves can miss the switch
        if expand_wiki_sections(device, host) or expand_wiki_sections(device, host):
            done.append(f"{host} expands every section of its articles")
        else:
            done.append(f"{host}: could not turn on \"Expand all sections\" in Special:MobileOptions, do it by hand")
    # Not a flag Chrome reads from its command line on Play images: a setting to change by hand
    done.append("Once per emulator, by hand: Chrome › Settings › Languages › turn off \"Offer to send pages "
                "in other languages to Google Translate\", or a \"Translate page?\" bar ends up in the captures")
    return done


def handle_popups(device: Device) -> bool:
    """Accepts a cookie wall or dismisses a popup, if one is on screen: returns whether it did."""
    nodes = device.nodes()
    # An exact button name first: a heading can also start with "Accept"
    found = next((node for node in nodes if node.label in ACCEPT), None) or next(
        (node for node in nodes if len(node.label) < 80 and node.label.lower() != "accepted"
         and node.label.lower().startswith(ACCEPT_PREFIXES)), None)
    found = found or next((node for node in nodes if node.text in DISMISS or node.description in DISMISS), None)
    if found:
        print(f"  tap: {found.label}")
        device.tap(found.bounds)
        time.sleep(1.5)
    return found is not None


def capture(device: Device, page_id: str, url: str, out: Path, source: dict[str, str], max_swipes: int = 40,
            timer: Timer | None = None) -> Path:
    """Captures ``url`` into ``out/<page_id>.json``, with its screenshots in ``out/<page_id>/``."""
    timer = timer or Timer()
    # Without it, harvest mode opens the permission's settings instead of scrolling the page
    if "allow" not in device.shell("appops", "get", APP, "SYSTEM_ALERT_WINDOW"):
        raise RuntimeError(f"Universal Copy may not draw over other apps: adb shell appops set {APP} SYSTEM_ALERT_WINDOW allow")
    device.shell(raw=f"rm -rf {SCREENS_DIR}")
    # Always the same tab: hundreds of tabs would slow Chrome down
    device.shell("am", "start", "-a", "android.intent.action.VIEW", "-d", url,
                 "-e", "com.android.browser.application_id", "smart-select", "com.android.chrome")
    loaded = wait_for_text(device)
    timer.lap("load")
    # Consent dialogs often show up a few seconds after the page: check again, except on sites
    # known to have none. Several popups can follow one another.
    for attempt in range(1 if any(site in url for site in QUIET_SITES) else 3):
        if not handle_popups(device) and attempt > 0:
            break
        if attempt == 0 and not any(site in url for site in QUIET_SITES):
            time.sleep(2)
    timer.lap("popups")
    # Copy mode reads whatever is in front: anything but the page would make a wrong capture
    if not loaded or "com.android.chrome" not in device.focus():
        raise RuntimeError(f"the page is not on screen: {device.focus()}")

    device.shell("am", "start", "-n", f"{APP}/.StartCopyModeActivity")
    if not wait_until(lambda: "CopyActivity" in device.focus(), timeout=45, interval=0.5):
        raise RuntimeError("copy mode did not open")
    timer.lap("copy mode")

    screens = out / page_id
    screens.mkdir(parents=True, exist_ok=True)
    count, reached_end, saved = scroll_to_end(device, max_swipes, timer)

    # The harvest: the file harvest mode saved once it stopped
    new = sorted(device.files() - saved)
    data = json.loads(device.shell("cat", f"{DEVICE_DIR}/{new[-1]}"))
    data.update(name=page_id, url=url, source=dict(source, url=url), reachedEnd=reached_end, screens=count)
    path = out / f"{page_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    device.fetch_screenshots(screens)
    timer.lap("save")
    return path


def wait_until(condition: Callable[[], object], timeout: float, interval: float = 2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return False


def wait_for_text(device: Device, timeout: float = 60, enough: int = 15) -> bool:
    """Waits until the screen shows some text: a page still loading would give an empty capture."""
    return wait_until(lambda: sum(1 for node in device.nodes() if len(node.label) > 3) >= enough, timeout, interval=0.5)


def settle(device: Device, timeout: float = 4) -> tuple[str, str]:
    """Waits until the page stops moving, and returns the hash of its pixels."""
    previous, deadline = device.page_hash(), time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.25)
        current = device.page_hash()
        if current == previous:
            return current
        previous = current
    return previous


def scroll_to_end(device: Device, max_swipes: int, timer: Timer | None = None) -> tuple[int, bool, set[str]]:
    """Scrolls in harvest mode until the page stops moving, saving each screen. Returns how many
    screens it saw, and whether it reached the end before ``max_swipes``.

    Harvest mode, unlike the Scroll Mode button whose behavior follows the app's settings, always
    selects everything and reads the screen again after each scroll. The end of the page is when a
    swipe leaves the page where it was, with swipes from the middle and from both sides: a swipe on
    a code block or a map can be taken by it instead of the page."""
    found: dict[str, Node] = {}

    def toolbar() -> bool:
        # One dump for both buttons: each takes about 2 s
        found.clear()
        found.update((node.label, node) for node in device.nodes() if node.label in ("Harvest mode", "More options"))
        return bool(found)

    # The toolbar slides in once the zones are drawn; the entry is an icon, or in the overflow menu
    if not wait_until(toolbar, timeout=30, interval=0.5):
        raise RuntimeError("no toolbar in copy mode")
    harvest = found.get("Harvest mode")
    if harvest is None:
        device.tap(found["More options"].bounds)
        time.sleep(1)
        harvest = next((node for node in device.nodes() if node.label == "Harvest mode"), None)
    if harvest is None:
        raise RuntimeError("no Harvest mode in copy mode's menu")
    device.tap(harvest.bounds)
    time.sleep(1.5)
    timer = timer or Timer()
    timer.lap("harvest start")

    page, screens, reached_end = settle(device), 0, False
    while True:
        device.save_screenshot(f"{screens:02d}.jpg")
        timer.lap("screenshots")
        screens += 1
        if screens > max_swipes:
            break
        moved = False
        for x, y in SWIPE_STARTS:
            device.swipe_up(x, y)
            timer.lap("swipes")
            # Harvest mode reads the screen once it has stopped
            current = settle(device)
            timer.lap("settle")
            # Both halves: a map swallows every drag that starts on it, and pans
            if current[0] != page[0] and current[1] != page[1]:
                page, moved = current, True
                break
        if not moved:
            reached_end = True
            break
    # Stopping cuts a screen read in progress short (Universal Copy 7.2.3): the last screen's read
    # must be over first. A long page's screen takes up to 2 s to read
    time.sleep(3)

    # The stop button, at the top right of harvest mode's bar, ends harvest mode and saves the harvest.
    # Tapped where it is drawn: the bar is an accessibility overlay, which uiautomator doesn't list,
    # and the page's nodes it lists there instead are the page's, under the bar
    saved = device.files()
    device.tap(STOP_BUTTON)
    # Copy mode saves a capture when it opens on the first screen, then the harvest's once it stops:
    # only a file written after the stop holds the harvest
    if not wait_until(lambda: device.files() - saved, timeout=30, interval=0.5):
        raise RuntimeError("harvest mode saved nothing after it stopped: is it a debug build?")
    timer.lap("harvest stop")
    return screens, reached_end, saved
