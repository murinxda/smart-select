"""Captures a web page the way Universal Copy reads it, on an Android emulator.

The capture drives the real app, so the blocks are exactly what smart select will get: a debug build
of Universal Copy saves each screen it reads, and in Scroll Mode the blocks of every screen the page
scrolls through. Needs:

- an emulator (or a phone) reachable with ``adb``, with Chrome;
- a debug build of Universal Copy installed, its accessibility service on.

The page is opened in Chrome, cookie walls are accepted and popups dismissed, then copy mode starts
and scrolls to the end of the page, like auto scroll does. A screenshot of each screen is saved next
to the capture, to check the labels against what the page looks like.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

APP = "com.camel.corp.universalcopy"
DEVICE_DIR = f"/sdcard/Android/data/{APP}/files/smart-select"

# Accepting cookies avoids "subscribe or accept" walls that hide the article. Notifications, sign-in
# and app banners are refused.
ACCEPT = [
    "Accepter", "Accepter et continuer", "Accept all", "Tout accepter", "J'accepte", "Accept", "Aceptar",
    "Accept and continue", "I agree", "Agree", "Agree and close", "ACCEPT AND CONTINUE", "Accepter & Fermer",
    "I Accept All", "Yes, I agree", "ACCEPTER LES COOKIES", "Accepter tout", "Tout accepter et continuer",
    "Alle akzeptieren", "Aceptar todo", "Aceitar",
]
ACCEPT_PREFIXES = ("j'accepte", "accept ", "tout accepter", "i accept", "agree")
# In pixels, the height of the navigation bar at the bottom of a 1080 x 2400 screen
NAVIGATION_BAR = 150

DISMISS = ["No thanks", "Not now", "No, thanks", "Close", "Fermer", "Use without an account", "Stay signed out"]


@dataclass(frozen=True)
class Node:
    text: str
    description: str
    bounds: tuple[int, int, int, int]

    @property
    def label(self) -> str:
        return self.text or self.description


class Device:
    def __init__(self, serial: str | None = None) -> None:
        self.adb = ["adb"] + (["-s", serial] if serial else [])

    def shell(self, *command: str, binary: bool = False) -> str | bytes:
        # The device's shell reads one command line: a URL's "&" must not end it
        line = " ".join(shlex.quote(part) for part in command)
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

    def swipe_up(self) -> None:
        self.shell("input", "swipe", "540", "1900", "540", "700", "400")

    def screenshot(self) -> bytes:
        return self.shell("screencap", "-p", binary=True)

    def page_pixels(self) -> bytes:
        """The raw pixels of the lower half of the page, above the navigation bar.

        Not the whole screen: harvest mode's counter keeps changing at the top, and at the end of a
        page, sticky headers come and go there as the page bounces."""
        raw = self.shell("screencap", binary=True)
        if len(raw) < 16:
            return raw
        width = int.from_bytes(raw[0:4], "little")
        height = int.from_bytes(raw[4:8], "little")
        # 4 bytes a pixel, after a header of 12 or 16 bytes depending on the Android version
        header = len(raw) - width * height * 4
        return raw[header + height // 2 * width * 4:header + (height - NAVIGATION_BAR) * width * 4]

    def focus(self) -> str:
        return self.shell("dumpsys", "window").partition("mCurrentFocus")[2].split("\n")[0]

    def files(self) -> set[str]:
        return set(self.shell("ls", DEVICE_DIR).split())


def capture_all(device: Device, sources: Path, out: Path, max_swipes: int = 40) -> tuple[int, list[str]]:
    """Captures every page of a sources CSV (id, url, license…) not captured yet in ``out``.

    A page that fails is logged and skipped: the next run tries it again. Returns how many pages were
    captured, and the ids of those that failed.
    """
    with sources.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    captured, failed = 0, []
    for number, row in enumerate(rows, 1):
        if (out / f"{row['id']}.json").exists():
            continue
        print(f"[{number}/{len(rows)}] {row['id']}", flush=True)
        try:
            source = {key: row[key] for key in ("license", "source", "category", "language")}
            path = capture(device, row["id"], row["url"], out, source, max_swipes)
            data = json.loads(path.read_text(encoding="utf-8"))
            end = "end" if data["reachedEnd"] else "cut"
            print(f"  {len(data.get('harvest') or [])} blocks, {end}", flush=True)
            captured += 1
        except Exception as error:  # one page must not stop the others
            print(f"  failed: {error}", flush=True)
            failed.append(row["id"])
        finally:
            for _ in range(3):
                device.shell("input", "keyevent", "KEYCODE_BACK")
                time.sleep(1)
            device.shell("input", "keyevent", "KEYCODE_HOME")
            time.sleep(2)
    return captured, failed


def setup(device: Device) -> list[str]:
    """Prepares a device for captures, once: returns what it did."""
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
    done.append("Universal Copy may draw over other apps, which Scroll Mode needs")
    return done


def accept_cookies(device: Device) -> None:
    for _ in range(2):
        nodes = device.nodes()
        # An exact button name first: a heading can also start with "Accept"
        found = next((node for node in nodes if node.label in ACCEPT), None) or next(
            (node for node in nodes if len(node.label) < 80 and node.label.lower() != "accepted"
             and node.label.lower().startswith(ACCEPT_PREFIXES)), None)
        if not found:
            return
        print(f"  accept cookies: {found.label}")
        device.tap(found.bounds)
        time.sleep(3)


def dismiss_popups(device: Device) -> None:
    for _ in range(3):
        found = next((node for node in device.nodes() if node.text in DISMISS or node.description in DISMISS), None)
        if not found:
            return
        print(f"  dismiss: {found.label}")
        device.tap(found.bounds)
        time.sleep(2)


def capture(device: Device, page_id: str, url: str, out: Path, source: dict[str, str], max_swipes: int = 40) -> Path:
    """Captures ``url`` into ``out/<page_id>.json``, with its screenshots in ``out/<page_id>/``."""
    # Without it, Scroll Mode opens the permission's settings instead of scrolling the page
    if "allow" not in device.shell("appops", "get", APP, "SYSTEM_ALERT_WINDOW"):
        raise RuntimeError(f"Universal Copy may not draw over other apps: adb shell appops set {APP} SYSTEM_ALERT_WINDOW allow")
    before = device.files()
    # Always the same tab: hundreds of tabs would slow Chrome down
    device.shell("am", "start", "-a", "android.intent.action.VIEW", "-d", url,
                 "-e", "com.android.browser.application_id", "smart-select", "com.android.chrome")
    loaded = wait_for_text(device)
    # Consent dialogs often show up a few seconds after the page
    for _ in range(2):
        accept_cookies(device)
        dismiss_popups(device)
        time.sleep(3)
    # Copy mode reads whatever is in front: anything but the page would make a wrong capture
    if not loaded or "com.android.chrome" not in device.focus():
        raise RuntimeError(f"the page is not on screen: {device.focus().strip()}")

    device.shell("am", "start", "-n", f"{APP}/.StartCopyModeActivity")
    if not wait_until(lambda: "CopyActivity" in device.focus(), timeout=45):
        raise RuntimeError("copy mode did not open")

    screens = out / page_id
    screens.mkdir(parents=True, exist_ok=True)
    reached_end = scroll_to_end(device, screens, max_swipes)

    new = sorted(device.files() - before)
    if not new:
        raise RuntimeError("Universal Copy saved no capture: is it a debug build?")
    data = json.loads(device.shell("cat", f"{DEVICE_DIR}/{new[-1]}"))
    data.update(name=page_id, url=url, source=dict(source, url=url), reachedEnd=reached_end)
    path = out / f"{page_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    for _ in range(3):
        if "CopyActivity" not in device.focus():
            break
        device.shell("input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.5)
    return path


def wait_until(condition: Callable[[], bool], timeout: float, interval: float = 2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return False


def wait_for_text(device: Device, timeout: float = 60, enough: int = 15) -> bool:
    """Waits until the screen shows some text: a page still loading would give an empty capture."""
    loaded = wait_until(lambda: sum(1 for node in device.nodes() if len(node.label) > 3) >= enough, timeout)
    if loaded:
        time.sleep(2)
    return loaded


def scroll_to_end(device: Device, screens: Path, max_swipes: int) -> bool:
    """Scrolls in harvest mode until the page stops moving, saving each screen. Returns whether it
    reached the end before ``max_swipes``.

    Harvest mode, unlike the Scroll Mode button whose behavior follows the app's settings, always
    selects everything and reads the screen again after each scroll."""
    def find(label: str) -> Node | None:
        return next((node for node in device.nodes() if node.label == label), None)

    # The toolbar slides in once the zones are drawn; the entry is an icon, or in the overflow menu
    if not wait_until(lambda: find("Harvest mode") or find("More options"), timeout=30):
        raise RuntimeError("no toolbar in copy mode")
    if not find("Harvest mode"):
        device.tap(find("More options").bounds)
        time.sleep(2)
    harvest = find("Harvest mode")
    if harvest is None:
        raise RuntimeError("no Harvest mode in copy mode's menu")
    device.tap(harvest.bounds)
    time.sleep(3)

    previous, reached_end = None, False
    for index in range(max_swipes + 1):
        # uiautomator doesn't see the page under harvest mode's overlay: its pixels do
        page = hashlib.sha1(device.page_pixels()).hexdigest()
        if page == previous:
            reached_end = True
            break
        previous = page
        (screens / f"{index:02d}.png").write_bytes(device.screenshot())
        if index < max_swipes:
            device.swipe_up()
            time.sleep(1.8)

    # The stop button, at the top right, ends Scroll Mode and saves the harvest
    stop = next((node.bounds for node in device.nodes()
                 if node.bounds[1] < 300 and node.bounds[0] > 900 and node.bounds[2] - node.bounds[0] < 200),
                (920, 170, 1020, 270))
    device.tap(stop)
    for _ in range(10):
        time.sleep(2)
        if "CopyActivity" in device.focus():
            break
    time.sleep(3)
    return reached_end
