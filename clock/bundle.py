"""Inline web/ into one self-contained HTML file (dist/incumbent-clock.html).

    python -m clock.bundle

Useful for hosting the demo anywhere that serves a single file. The page is
identical to web/index.html; the data, CSS and JS are simply inlined.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
FONTS = ("https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@"
         "0,8..60,300..700;1,8..60,300..700&display=swap")


def bundle(out: Path, embedded: bool = True) -> Path:
    css = (WEB / "style.css").read_text()
    js = (WEB / "app.js").read_text()
    # Legistar's own text contains U+FFFD where the city's export lost a character. Inside the JSON
    # those only ever appear in strings, so write them as the escape \\ufffd (same value, ASCII-safe).
    data = (WEB / "data" / "site.js").read_text().replace("\ufffd", "\\ufffd")
    html = f"""<meta charset="utf-8">
<title>Incumbent Clock</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet">
<style>
{css}
</style>
<main class="page" id="app"></main>
<script>{data}</script>
<script>window.EMBEDDED = {"true" if embedded else "false"};</script>
<script>
{js}
</script>
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = bundle(ROOT / "dist" / "incumbent-clock.html")
    print(f"{p} ({p.stat().st_size / 1e6:.1f} MB)")
