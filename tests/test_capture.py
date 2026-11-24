from smart_select import capture
from smart_select.capture import Node, handle_all_popups, handle_popups


class Screen:
    """A device whose screen shows, at each look, the next list of buttons."""

    def __init__(self, *screens: list[str]):
        self.screens = list(screens)
        self.looks = 0
        self.taps: list[str] = []
        self.swipes = 0

    def nodes(self) -> list[Node]:
        names = self.screens[min(self.looks, len(self.screens) - 1)]
        self.looks += 1
        return [Node(name, "", (0, 0, 10, 10)) for name in names]

    def tap(self, bounds):
        self.taps.append(self.screens[min(self.looks - 1, len(self.screens) - 1)][0])

    def swipe_up(self, x, y):
        self.swipes += 1


def test_the_consent_buttons_of_the_commercial_sites_are_accepted(monkeypatch):
    monkeypatch.setattr(capture.time, "sleep", lambda seconds: None)
    for name in ["Accepter tous les cookies", "Oui, j’accepte", "Allow all", "I ACCEPT",
                 "Accepter et fermer: Accepter notre traitement des données et fermer", "Aceptar y cerrar",
                 "Acepta y accede a EL MUNDO"]:
        assert handle_popups(Screen([name])), name


def test_a_heading_that_starts_like_a_button_is_not_tapped(monkeypatch):
    monkeypatch.setattr(capture.time, "sleep", lambda seconds: None)
    assert not handle_popups(Screen(["Accepted: the long story of a word " * 3]))
    # A link in the article: tapping it leaves the page
    assert not handle_popups(Screen(["agreed to pay $7.25 billion"]))
    assert handle_popups(Screen(["Agree and proceed"]))


def test_a_consent_wall_that_shows_up_late_is_still_accepted(monkeypatch):
    monkeypatch.setattr(capture.time, "sleep", lambda seconds: None)
    device = Screen(["Menu"], ["Menu"], ["Menu"], ["I ACCEPT"], ["Menu"])
    handle_all_popups(device)
    assert device.taps == ["I ACCEPT"]
    # One more look after the tap finds nothing, and it stops there
    assert device.looks == 5


def test_a_notification_popup_is_refused_whatever_the_case_of_its_button(monkeypatch):
    monkeypatch.setattr(capture.time, "sleep", lambda seconds: None)
    device = Screen(["No, Thanks", "Allow"])
    assert handle_popups(device)
    assert device.taps == ["No, Thanks"]


def test_a_button_below_the_screen_is_scrolled_to_before_it_is_tapped(monkeypatch):
    monkeypatch.setattr(capture.time, "sleep", lambda seconds: None)

    class Dialog(Screen):
        def nodes(self):
            self.looks += 1
            # Zero height below the screen until the dialog is dragged up
            return [Node("Accept All", "", (36, 1900, 1013, 2000) if self.swipes else (36, 2299, 1013, 2299))]

        def tap(self, bounds):
            self.taps.append(bounds)

    device = Dialog([])
    assert handle_popups(device)
    assert device.swipes == 1 and device.taps == [(36, 1900, 1013, 2000)]


def test_a_close_button_below_the_screen_does_not_scroll_the_page(monkeypatch):
    monkeypatch.setattr(capture.time, "sleep", lambda seconds: None)

    class Page(Screen):
        def nodes(self):
            self.looks += 1
            return [Node("Close", "", (36, 2299, 1013, 2299))]

    device = Page([])
    assert not handle_popups(device)
    assert device.swipes == 0
