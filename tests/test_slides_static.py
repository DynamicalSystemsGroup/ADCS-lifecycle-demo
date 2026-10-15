"""Static slide fragments (talk/slides/*.html): structure, word budget, CTA link, banned words."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

SLIDES = Path(__file__).resolve().parent.parent / "talk" / "slides"
FRAGMENTS = sorted(SLIDES.glob("*.html"))
CONTRIBUTE = "https://github.com/Open-MBEE"  # the QR target on the call to action
BANNED = re.compile(r"proof|proved|verified satisfied|the truth|neighbo|human-validated", re.I)
BUDGET = {"cta": 160, "f2": 66, "envelope": 70, "tools": 200, "thesis": 40, "se-v": 42, "geosat": 70}  # cta: three numbered tasks; f2: its four builds together; thesis: Michael's three-line caption; others 20


class _Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h2 = 0
        self.h2_plain = 0  # h2 without a build marker
        self.depth = {"svg": 0, "style": 0}
        self.words: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "h2":
            self.h2 += 1
            self.h2_plain += "data-s" not in dict(attrs)
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


def test_all_fragments_exist():
    ids = {f.stem for f in FRAGMENTS}
    assert ids == set((SLIDES / "order.txt").read_text().split())
    assert {"h0", "m1", "m2", "f2", "evidence-kinds-callback", "cta", "thesis", "stack"} <= ids


@pytest.mark.parametrize("frag", FRAGMENTS, ids=lambda f: f.stem)
def test_fragment_structure(frag):
    scan = _scan(frag)
    assert scan.h2 == 1 or (scan.h2 > 1 and scan.h2_plain == 0), "one h2, or one per build"
    assert len(scan.words) <= BUDGET.get(frag.stem, 20), scan.words
    assert not any(scan.depth.values()), "unbalanced svg/style tags"
    assert "<style" not in frag.read_text(), "styles belong in deck.css"


@pytest.mark.parametrize("frag", FRAGMENTS, ids=lambda f: f.stem)
def test_no_banned_words(frag):
    assert not BANNED.search(frag.read_text())


def test_cta_contains_contribute_url():
    assert CONTRIBUTE in (SLIDES / "cta.html").read_text()
