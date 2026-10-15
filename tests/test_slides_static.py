"""Static slide fragments (talk/slides/*.html): structure, word budget, CTA link, banned words."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

SLIDES = Path(__file__).resolve().parent.parent / "talk" / "slides"
FRAGMENTS = sorted(SLIDES.glob("*.html"))
CONTRIBUTE = "https://github.com/Open-MBEE/open-mbee.github.io/wiki/Contribute"
BANNED = re.compile(r"proof|verified satisfied|the truth", re.I)


class _Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h2 = 0
        self.depth = {"svg": 0, "style": 0}
        self.words: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "h2":
            self.h2 += 1
        if tag in self.depth:
            self.depth[tag] += 1

    def handle_endtag(self, tag):
        if tag in self.depth:
            self.depth[tag] -= 1

    def handle_data(self, data):
        if not any(self.depth.values()):
            self.words += [w for w in data.split() if re.search(r"\w", w)]


def _scan(path: Path) -> _Scan:
    scan = _Scan()
    scan.feed(path.read_text())
    scan.close()
    return scan


def test_all_eight_fragments_exist():
    ids = {f.stem for f in FRAGMENTS}
    assert ids == set((SLIDES / "order.txt").read_text().split())
    assert len(ids) == 8


@pytest.mark.parametrize("frag", FRAGMENTS, ids=lambda f: f.stem)
def test_fragment_structure(frag):
    scan = _scan(frag)
    assert scan.h2 == 1
    assert len(scan.words) <= 20, scan.words
    assert not any(scan.depth.values()), "unbalanced svg/style tags"
    assert "<style" not in frag.read_text(), "styles belong in deck.css"


@pytest.mark.parametrize("frag", FRAGMENTS, ids=lambda f: f.stem)
def test_no_banned_words(frag):
    assert not BANNED.search(frag.read_text())


def test_cta_contains_contribute_url():
    assert CONTRIBUTE in (SLIDES / "cta.html").read_text()
