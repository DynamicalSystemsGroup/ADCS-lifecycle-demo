"""Preview static slide fragments as 1280x800 pages, optionally screenshotting them.

Each fragment (talk/slides/<id>.html) is wrapped with deck.css in a white frame that imitates a
marimo slide: a Lora h2 top-left and a PT Sans body from Google Fonts (preview only). The token
``asset:NAME`` in a fragment resolves to talk/assets/NAME.

    uv run python scripts/preview_slides.py --out output/slide-preview
    uv run python scripts/preview_slides.py --out output/slide-preview --shots output/slide-shots
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FONTS = (
    "https://fonts.googleapis.com/css2?family=Lora:wght@500;600;700"
    "&family=PT+Sans:wght@400;700&display=swap"
)
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{name}</title>
<link rel="stylesheet" href="{fonts}">
<style>
html, body {{ margin: 0; background: #ffffff; }}
.frame {{ width: 1280px; height: 800px; box-sizing: border-box; padding: 40px 50px 0; overflow: hidden; background: #ffffff; }}
{css}
</style></head>
<body><div class="frame">
{fragment}
</div></body></html>
"""

app = typer.Typer(add_completion=False, help=__doc__)


def build_pages(slides: Path, assets: Path, out: Path) -> list[Path]:
    css = (slides / "deck.css").read_text()
    out.mkdir(parents=True, exist_ok=True)
    pages = []
    order = slides / "order.txt"  # slide order, one id per line; else alphabetical
    ids = order.read_text().split() if order.exists() else sorted(f.stem for f in slides.glob("*.html"))
    for frag in (slides / f"{i}.html" for i in ids if (slides / f"{i}.html").exists()):
        body = frag.read_text().replace("asset:", assets.resolve().as_uri() + "/")
        page = out / frag.name
        page.write_text(PAGE.format(name=frag.stem, fonts=FONTS, css=css, fragment=body))
        pages.append(page)
    return pages


def screenshot(page: Path, png: Path) -> None:
    subprocess.run(
        [CHROME, "--headless=new", "--hide-scrollbars", f"--screenshot={png}",
         "--window-size=1280,800", "--virtual-time-budget=6000", page.resolve().as_uri()],
        check=True, capture_output=True,
    )


@app.command()
def main(
    slides: Path = typer.Option(ROOT / "talk" / "slides", help="Fragment directory (with deck.css)."),
    assets: Path = typer.Option(ROOT / "talk" / "assets", help="Directory behind the asset: token."),
    out: Path = typer.Option(ROOT / "output" / "slide-preview", help="Where the pages are written."),
    shots: Path | None = typer.Option(None, help="If set, screenshot each page here (headless Chrome)."),
) -> None:
    pages = build_pages(slides, assets, out)
    for i, page in enumerate(pages, 1):
        typer.echo(page)
        if shots:
            shots.mkdir(parents=True, exist_ok=True)
            screenshot(page, shots / f"{i:02d}-{page.stem}.png")


if __name__ == "__main__":
    app()
