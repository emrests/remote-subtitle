from rsub.layout import fit, font_path, render
from rsub.store import DEFAULT_STYLE

STYLE = dict(DEFAULT_STYLE)
LINE = [{"speaker": "Arthur", "color": "#ff4d4d", "en": "x", "tr": "Merhaba dostum!"}]
LONG = [{"speaker": None, "color": None, "en": "x",
         "tr": "Valentine ahırlarında at malzemeleri konusunda çok geniş bir ürün yelpazesi bulunuyor, bir göz at."}]


def test_font_path_lookup():
    assert font_path("Arial").lower().endswith("arial.ttf")
    assert font_path("Arial", bold=True).lower().endswith("arialbd.ttf")
    assert font_path("Cambria").lower().endswith("cambria.ttc")
    assert font_path("Yok Böyle Font").lower().endswith("segoeui.ttf")


def test_short_text_keeps_scaled_size():
    size, rows = fit(LINE, STYLE, 1800, 200, scale=1.0)
    assert size == STYLE["size"] and len(rows) == 1


def test_long_text_wraps_and_shrinks_into_box():
    size, rows = fit(LONG, STYLE, 600, 90, scale=1.0)
    assert size < STYLE["size"] and len(rows) >= 2
    assert all(w <= 600 for w in (r["width"] for r in rows))
    assert sum(r["height"] for r in rows) <= 90


def test_render_covers_whole_region():
    img = render(LINE, STYLE, 900, 120, scale=1.0)
    assert img.size == (900, 120) and img.mode == "RGBA"
    assert img.getpixel((2, 2))[3] >= 230 and img.getpixel((897, 117))[3] >= 230  # köşeler de kapalı


def test_render_name_has_speaker_color():
    img = render(LINE, STYLE, 900, 120, scale=1.0)
    b = img.tobytes()
    reds = [i for i in range(0, len(b), 4) if b[i] > 200 and b[i + 1] < 120 and b[i + 2] < 120]
    assert reds  # "Arthur:" kırmızı çizildi


def test_render_nothing_for_empty():
    assert render([], STYLE, 900, 120, scale=1.0) is None
