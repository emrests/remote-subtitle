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


def test_render_has_rounded_corners():
    img = render(LINE, STYLE, 900, 120, scale=1.0)
    assert img.size == (900, 120) and img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0 and img.getpixel((899, 119))[3] == 0  # köşe dışı saydam
    assert img.getpixel((450, 3))[3] > 0  # kenar ortası dolu


def test_render_respects_opacity_without_backdrop():
    style = {**STYLE, "bgOpacity": 0.3}
    img = render([{**LINE[0], "speaker": None, "tr": "."}], style, 900, 120, scale=1.0)
    assert abs(img.getpixel((40, 60))[3] - 77) <= 2  # zorunlu %92 yok


def test_backdrop_is_blurred_and_opaque():
    from PIL import Image, ImageDraw
    src = Image.new("RGB", (900, 120), "white")
    d = ImageDraw.Draw(src)
    for x in range(0, 900, 6):
        d.line([(x, 0), (x, 119)], fill="black", width=3)  # keskin çizgiler = "İngilizce yazı"
    style = {**STYLE, "bgOpacity": 0.0, "blur": 16}
    img = render([{**LINE[0], "speaker": None, "tr": "."}], style, 900, 120, scale=1.0, backdrop=src)
    row = [img.getpixel((x, 60)) for x in range(100, 300)]
    assert all(p[3] == 255 for p in row)  # bulanık zemin opak: alttaki yazı görünmez
    lum = [p[0] for p in row]
    assert max(lum) - min(lum) < 60  # çizgiler eridi (kaynakta fark 255)


def test_render_name_has_speaker_color():
    img = render(LINE, STYLE, 900, 120, scale=1.0)
    b = img.tobytes()
    reds = [i for i in range(0, len(b), 4) if b[i] > 200 and b[i + 1] < 120 and b[i + 2] < 120]
    assert reds  # "Arthur:" kırmızı çizildi


def test_render_nothing_for_empty():
    assert render([], STYLE, 900, 120, scale=1.0) is None


def test_pill_hugs_text_at_english_position():
    from rsub.layout import pill
    anchor = (700, 40, 180, 50)  # İngilizce "Help me!" bölgede burada
    (x, y, w, h), _ = pill(LINE, STYLE, 1600, 400, 1.0, anchor)
    assert w < 1000 and h < 200  # bölgenin tamamı değil
    assert x <= 700 and x + w >= 880 and y <= 40 and y + h >= 90  # İngilizceyi tamamen kapatır
    assert abs((x + w / 2) - 790) <= 2 and abs((y + h / 2) - 65) <= 2  # aynı yerde ortalı
    assert x >= 0 and y >= 0 and x + w <= 1600 and y + h <= 400


def test_pill_without_anchor_centers_in_region():
    from rsub.layout import pill
    (x, y, w, h), _ = pill(LINE, STYLE, 1600, 400, 1.0, None)
    assert abs((x + w / 2) - 800) <= 2 and abs((y + h / 2) - 200) <= 2 and w < 1600


def test_pill_clamped_inside_region():
    from rsub.layout import pill
    (x, y, w, h), _ = pill(LONG, STYLE, 1600, 400, 1.0, (0, 0, 60, 30))
    assert x >= 0 and y >= 0 and x + w <= 1600 and y + h <= 400


def test_render_with_fitted_pill_keeps_rows():
    from rsub.layout import pill
    (x, y, w, h), fitted = pill(LONG, STYLE, 1600, 400, 1.0, None)
    img = render(LONG, STYLE, w, h, 1.0, fitted=fitted)
    assert img.size == (w, h)


TWO_LINE_TR = [{"speaker": None, "color": None, "en": "x",
                "tr": "Pekala, geldiğimiz yolu geri takip edemeyiz. Hadi bu yolu deneyelim o zaman."}]










def test_pill_leaves_margin_for_game_subtitle_box():
    from rsub.layout import pill
    short = [{"speaker": None, "color": None, "en": "x", "tr": "Ok."}]  # İngilizce uzun, Türkçe çok kısa
    (x, y, w, h), _ = pill(short, STYLE, 1600, 400, 1.0, (500, 150, 300, 36))
    assert y <= 150 - 12 and y + h >= 186 + 12  # oyunun kendi koyu kutusu yazıdan ~10-15 px taşar
    assert x <= 500 - 28 and x + w >= 800 + 28  # RDR2: kutu yanlara satır yüksekliğinin ~%75'i kadar taşıyor


def test_blur_strong_enough_to_erase_text_under_pill():
    from PIL import Image, ImageDraw
    src = Image.new("RGB", (600, 70), (30, 30, 30))
    ImageDraw.Draw(src).rectangle([40, 17, 560, 53], fill="white")  # 36 px yüksek beyaz "yazı" şeridi
    style = {**STYLE, "bgOpacity": 0.0, "blur": 4}  # kullanıcı düşük bulanıklık seçse bile
    img = render([{**LINE[0], "speaker": None, "tr": "."}], style, 600, 70, scale=1.0, backdrop=src)
    col = [img.getpixel((120, y))[0] for y in range(8, 62)]  # Türkçe "." ortada; ondan uzak sütun
    assert max(col) - min(col) < 70  # şerit eridi: kenarla orta arasında keskin fark yok


def _ink_box(img):
    """Beyaz yazı piksellerinin (zemin koyu) kapsadığı satır aralığı."""
    w, h = img.size
    rows = [y for y in range(h) if any(img.getpixel((x, y))[0] > 200 for x in range(0, w, 2))]
    return rows[0], rows[-1]


def test_text_vertically_centered_in_pill():
    style = {**STYLE, "bg": "#000000", "bgOpacity": 1.0, "blur": 0}
    for tr in ("HELLO THERE", "Kısa."):
        img = render([{"speaker": None, "color": None, "en": "x", "tr": tr}], style, 500, 90, scale=1.0)
        top, bottom = _ink_box(img)
        assert abs(top - (90 - 1 - bottom)) <= 4, (tr, top, 89 - bottom)  # üst ve alt boşluk eşit


def test_blank_pill_covers_without_text():
    from rsub.layout import pill
    (x, y, w, h), fitted = pill([], STYLE, 1600, 400, 1.0, (500, 150, 300, 36))
    assert x <= 500 and x + w >= 800 and y <= 150 and y + h >= 186
    img = render([], {**STYLE, "bgOpacity": 1.0, "blur": 0}, w, h, 1.0, fitted=fitted, blank=True)
    assert img is not None and img.size == (w, h)
    b = img.tobytes()
    assert not any(b[i] > 200 for i in range(0, len(b), 4))  # beyaz yazı yok, sadece zemin



def test_pill_font_comes_from_style_not_original():
    from rsub.layout import pill
    for orig_h in (30, 80):  # orijinal altyazı küçük de olsa büyük de olsa
        _, (px, _) = pill(LINE, STYLE, 1600, 400, 1.5, (300, 60, 700, orig_h))
        assert px == round(STYLE["size"] * 1.5)


def test_pill_shrinks_when_text_does_not_fit_region():
    from rsub.layout import pill
    (x, y, w, h), (px, rows) = pill(TWO_LINE_TR, STYLE, 300, 60, 1.0, None)
    assert w <= 300 and h <= 60 and px < STYLE["size"]
