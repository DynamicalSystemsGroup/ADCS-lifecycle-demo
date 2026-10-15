"""Page a static marimo slides export one slide at a time.

`marimo export html` renders a slides-layout notebook as one vertical scroll (the static
viewer ignores the layout). This injects a small stylesheet and script so each cell (one
cell = one slide) shows alone: arrow keys / PageUp / PageDown or the corner buttons move
between slides, and `#n` links to slide n.

    uv run python scripts/static_deck.py _site/osa/index.html
"""

from __future__ import annotations

import sys
from pathlib import Path

MARK = "<!-- static-deck -->"

INJECT = MARK + """
<style>
body.deck { overflow: hidden; }
body.deck .marimo-cell { display: none !important; }
body.deck .marimo-cell.on { display: block !important; position: fixed; inset: 0; z-index: 50;
  max-width: 1280px; margin: 0 auto; padding: 3vh 3vw 56px; overflow: auto; background: #ffffff; }
#deck-nav { position: fixed; right: 16px; bottom: 12px; z-index: 60; display: flex; gap: 8px;
  align-items: center; font: 14px sans-serif; color: #6b7280; }
#deck-nav button { font: inherit; border: 1px solid #d1d5db; background: #ffffff; color: #111111;
  border-radius: 6px; padding: 2px 10px; cursor: pointer; }
</style>
<script>
(function () {
  function start(cells) {
    var i = 0, nav = document.createElement("div");
    nav.id = "deck-nav";
    nav.innerHTML = '<button type="button" aria-label="previous slide">&lsaquo;</button>' +
      '<span></span><button type="button" aria-label="next slide">&rsaquo;</button>';
    document.body.appendChild(nav);
    var b = nav.querySelectorAll("button"), n = nav.querySelector("span");
    function go(k) {
      i = Math.max(0, Math.min(cells.length - 1, k));
      cells.forEach(function (c, j) { c.classList.toggle("on", j === i); });
      n.textContent = (i + 1) + " / " + cells.length;
      history.replaceState(null, "", "#" + (i + 1));
    }
    b[0].onclick = function () { go(i - 1); };
    b[1].onclick = function () { go(i + 1); };
    addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight" || e.key === "PageDown") go(i + 1);
      if (e.key === "ArrowLeft" || e.key === "PageUp") go(i - 1);
    });
    document.body.classList.add("deck");
    go((parseInt(location.hash.slice(1), 10) || 1) - 1);
  }
  var tries = 0, t = setInterval(function () {
    var cells = Array.prototype.slice.call(document.querySelectorAll(".marimo-cell"));
    if (cells.length || ++tries > 300) { clearInterval(t); if (cells.length) start(cells); }
  }, 100);
})();
</script>
"""


def inject(html: str) -> str:
    if MARK in html:
        return html
    i = html.rindex("</body>")
    return html[:i] + INJECT + html[i:]


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        p = Path(arg)
        p.write_text(inject(p.read_text(encoding="utf-8")), encoding="utf-8")
