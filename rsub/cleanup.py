"""OCR çıktısını çeviriden önce temizler: 1 harflik okuma hatalarını düzeltir, çöp okumaları puanlar.

Türkçe OCR paketi İngilizce sözlük bilmediği için ara sıra harf karıştırır (course → couxse) ya da harf harf
beliren/parlak zemindeki yazıyı anlamsız şekillere çevirir ("2LİÇJ3", "e!jîî"). Kelimelerin ne kadarının
İngilizce sözlükte (ya da bilinen isim) olduğuna bakarak 0–1 arası bir puan verilir; düşük puanlı okumalar
çevrilmez.
"""
import re

from spellchecker import SpellChecker

_SP = SpellChecker(language="en", distance=1)  # yalnız 1 harf: 2 harf hem yavaş (~150 ms) hem riskli
_TOKEN = re.compile(r"[^\W\d_][\w'’]*|\S*\d\S*", re.UNICODE)
_ASCII_WORD = re.compile(r"^[A-Za-z][A-Za-z'’]*$")
_SENTENCE_END = ".!?…:\"“"
GARBAGE_BELOW = 0.6
_EDGE_NUMBERS = re.compile(r"^\s*\d+\s+|\s+\d+\s*$")
_STRAY_LETTER = re.compile(r"^\s*[B-HJ-Zb-z]\s+(?=\S)")  # satır başında yalnız harf ("Z No.") — A/I/a değil
# Türkçe OCR paketi İngilizce harfleri Türkçe benzerleriyle karıştırır ("leşs" → "less")
_TR_TO_ASCII = str.maketrans("şçğıİöüîâûŞÇĞÖÜÎÂÛ", "scgiIouiauSCGOUIAU")


def _split_merged(core: str) -> str | None:
    """Bitişik okunmuş iki kelimeyi ayırır ("ifhe" → "if he"); iki parça da sözlükte olmalı."""
    best = None
    for i in range(2, len(core) - 1):
        a, b = core[:i], core[i:]
        if a in _SP and b in _SP and (best is None or min(len(a), len(b)) > min(map(len, best))):
            best = (a, b)
    return " ".join(best) if best else None


def _core(word: str) -> str:
    return re.sub(r"['’]s$", "", word).lower().replace("’", "'")


def clean(text, known: set[str]):
    """(düzeltilmiş metin, puan) döner. Metin OcrText ise kutu/satır bilgisi korunur."""
    ok = total = 0
    out, pos = [], 0
    s = _EDGE_NUMBERS.sub("", str(text))  # satır başı/sonundaki yalnız sayılar arayüz rakamıdır ("47 Get to…")
    s = _STRAY_LETTER.sub("", s)
    for m in _TOKEN.finditer(s):
        word = m.group(0)
        out.append(s[pos:m.start()])
        pos = m.end()
        before = s[: m.start()].rstrip()
        sentence_start = not before or before[-1] in _SENTENCE_END
        if not _ASCII_WORD.match(word) and re.search(r"[A-Za-z]", word):
            ascii_word = word.translate(_TR_TO_ASCII)
            if _ASCII_WORD.match(ascii_word):
                word = ascii_word  # Türkçe harf karışması: düzelt ve normal kelime gibi değerlendir
        fixed = word
        total += 1
        if (len(word) == 1 and word not in "aAI") or not _ASCII_WORD.match(word):
            pass  # tek harf (yarım okuma "t"), rakam ya da Türkçe harf: İngilizce olamaz → çöp
        elif _core(word) in _SP or word in known:
            ok += 1
        elif word[0].isupper() and not sentence_start:
            ok += 1  # cümle ortasında büyük harf: isim, dokunma
        elif not word[0].isupper() and (split := _split_merged(_core(word))):
            fixed = split  # "ifhe" → "if he"
            ok += 1
        else:
            cand = _SP.correction(_core(word))
            if cand and cand != _core(word):  # 1 harf farkla gerçek kelime: couxse → course
                fixed = cand.capitalize() if word[0].isupper() else cand
                ok += 1
            elif word[0].isupper():
                ok += 1  # cümle başında bilinmeyen büyük harfli kelime: muhtemelen isim (Mierda)
        out.append(fixed)
    out.append(s[pos:])
    result = "".join(out)
    if hasattr(text, "box"):  # OcrText: konum/satır bilgisini taşı
        new = type(text)(result)
        new.box, new.lines = text.box, getattr(text, "lines", 0)
        new.name_colors = getattr(text, "name_colors", {})
        result = new
    return result, (ok / total if total else 0.0)
