"""scripts/static_deck.py: the paging overlay for the static export of the OSA deck."""

from scripts.static_deck import MARK, inject


def test_inject_once_before_body_close():
    html = "<html><body><div class='marimo-cell'></div></body></html>"
    out = inject(html)
    assert out.count(MARK) == 1 and out.index(MARK) < out.rindex("</body>")
    assert inject(out) == out  # idempotent
