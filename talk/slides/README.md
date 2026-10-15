# Static slide fragments

Eight HTML fragments (one slide each), the shared stylesheet `deck.css`, and `order.txt` (slide order).
Visual rules: see the art direction for the talk (Lora h2, PT Sans body, amber = a person decided, blue = computed).

## Using a fragment from marimo (spike result)

Spike: a scratch notebook with `mo.Html('<style>...</style><h2 class="x">...</h2><svg>...<style>...</style></svg>')`,
exported with `marimo export html`, screenshotted in headless Chrome. Result: **`<style>` blocks apply**, both in the
HTML and inside an inline SVG. So the helper prepends the text of `deck.css` as a `<style>` block to the fragment.

Notes for the helper (WP20):
- A `<style>` in `mo.Html` is page-global. Every rule in `deck.css` is scoped under `.slide`; keep it that way.
- Fragments hold no `<style>` of their own (a test enforces this).
- `framework.html` has `<img src="asset:framework-layers.png">`. Replace the `asset:` token with a data URI or a served URL.
- Fonts (Lora, PT Sans) come from marimo's slide theme; `scripts/preview_slides.py` loads them from Google Fonts for previews only.
- Footnotes are `<p class="src">` or, where the on-screen word budget (20, outside SVG) needs it, a one-line `<svg class="src">`.
- Each `.slide` is 700px tall, up to 1180px wide; SVGs scale with the width.
- Placeholders: the Git SHAs in `lineage.html` (3f2a9c1 and so on) are illustrative, not real commits.

## Preview

    uv run python scripts/preview_slides.py --out output/slide-preview --shots output/slide-shots
