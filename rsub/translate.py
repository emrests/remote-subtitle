"""Ollama ile İngilizce → Türkçe çeviri; isim/terim koruma ve önbellek.

İsimler ve terim listesi modele talimatla verilmez: TranslateGemma talimatı da çevirip ekrana basıyordu
("Bu sabit çevirileri kullanın: Dutch = Hollandaca"). Bunun yerine korunacak her ifade çeviriden önce
uydurma bir isimle (Zorvak gibi) değiştirilir, çeviriden sonra geri konur. Model uydurma ismi çevirmez ve
Türkçe ekleri doğal biçimde ekler: "Zorvak'a" → "Dutch'a". Ölçüm: 5/5 cümlede korundu.
"""
import json
import re
import urllib.request

# "localhost" değil: Windows önce ::1'i dener, Ollama yalnız 127.0.0.1'de dinler → istek başına ~2 sn kayıp
OLLAMA = "http://127.0.0.1:11434"
PROMPT = (
    "You are a professional English (en) to Turkish (tr) translator. Your goal is to accurately "
    "convey the meaning and nuances of the original English text while adhering to Turkish grammar, "
    "vocabulary, and cultural sensitivities. Produce only the Turkish translation, without any "
    "additional explanations or commentary. Please translate the following English text into Turkish:"
    "\n\n\n{text}"
)

# Yer tutucular ismin son ünlüsüne göre seçilir ki Türkçe ek de uysun (Sadie → Tavrin'i → Sadie'yi değil ama
# en azından ince ünlülü ek). Kalın düz: a/ı, ince: e/i, kalın yuvarlak: o/u.
PLACEHOLDERS = {
    "back": ["Zorvak", "Kelmar", "Tarvan", "Vasdar", "Morkan", "Galdar"],
    "front": ["Tavrin", "Melzik", "Kestin", "Dorvil", "Selvik", "Brenil"],
    "round": ["Rivon", "Dalgor", "Mekrun", "Tasbur", "Velkon", "Zandor"],
    "frontround": ["Zemdül", "Melgöz", "Velkür", "Dersün", "Kortün", "Selmür"],  # ölçüm: en az "ürün" sanılan
}
# Unvan + isim tek birim; unvanın noktası cümle sonu değildir. Türkçe karşılığı (yoksa olduğu gibi).
TITLES = {"Mr": "Bay", "Mrs": "Bayan", "Ms": "Bayan", "Miss": "Bayan", "Mister": "Bay", "Madam": "Madam",
          "Dr": "Dr.", "St": "St.", "Capt": "Yzb.", "Col": "Alb.", "Gen": "Gen.", "Lt": "Tğm.", "Sgt": "Çvş.",
          "Rev": "Peder", "Prof": "Prof.", "Sir": "Sir", "Lady": "Leydi", "Lord": "Lord"}
_TITLE = re.compile(r"(?<![\w'’])(" + "|".join(sorted(TITLES, key=len, reverse=True))
                    + r")\.?\s+([A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*)")
_CAPS = re.compile(r"(?<![\w'’])([A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*)")
_POSSESSIVE = re.compile(r"['’]s$")
_REFUSAL = re.compile(r"^(Üzgünüm|Maalesef|Özür dilerim)\b.*(metn|bağlam|anlam|çevir)", re.IGNORECASE | re.DOTALL)


def _vowel_class(word: str) -> str:
    """Son ünlüye göre Türkçe ek sınıfı. İngilizce isimde yazıma bakılır; Türkçe karşılıkta ı/ö/ü de dikkate alınır."""
    vowels = [c for c in word.lower() if c in "aeıioöuüy"]
    last = vowels[-1] if vowels else "a"
    if last in "öü":
        return "frontround"
    return "round" if last in "ou" else "front" if last in "eiy" else "back"


def _is_name_word(word: str) -> bool:
    if word == "I" or word.startswith(("I'", "I’")):
        return False
    core = _POSSESSIVE.sub("", word)
    return not (len(core) > 1 and core.isupper())  # WARNING, OK gibi


def protect(text: str, glossary: dict[str, str], known: set[str]) -> tuple[str, dict[str, str]]:
    """Korunacak ifadeleri yer tutucuyla değiştirir. (maskeli metin, {yer tutucu: konacak metin}) döner.
    Korunanlar: terim listesi (→ Türkçe karşılığı), cümle ortasındaki büyük harfli isimler,
    bilinen isimler (karakterler, daha önce görülenler) cümle başında bile."""
    mapping: dict[str, str] = {}
    used = {w for pool in PLACEHOLDERS.values() for w in pool if w in text}  # metinde zaten geçenleri kullanma

    def place(original: str, target: str) -> str:
        pool = PLACEHOLDERS[_vowel_class(target)]  # ek, yerine konacak metne uymalı (Ölü Göz → "ü")
        ph = next((p for p in pool if p not in used), None) or f"Zorvak{len(mapping) + 2}"
        used.add(ph)
        mapping[ph] = target
        return ph

    for en in sorted((k for k in glossary if k.strip()), key=len, reverse=True):
        pattern = re.compile(rf"(?<![\w]){re.escape(en)}(?![\w])", re.IGNORECASE)
        text = pattern.sub(lambda m: place(m.group(0), glossary[en]), text)

    def title_repl(m: re.Match) -> str:  # "Mr. Morgan" → "Bay Morgan" (cümle başında da)
        phrase = m.group(2)
        name = _POSSESSIVE.sub("", phrase)
        return place(name, f"{TITLES[m.group(1)]} {name}") + phrase[len(name):]
    text = _TITLE.sub(title_repl, text)

    def repl(m: re.Match) -> str:
        words = m.group(1).split()
        before = text[: m.start()].rstrip()
        if not before or before[-1] in ".!?…:\"“":  # cümle başı: ilk kelime ancak biliniyorsa isimdir
            if _POSSESSIVE.sub("", words[0]) not in known:
                lead, words = words[0], words[1:]
                if not words:
                    return m.group(0)
                return lead + " " + repl_words(words)
        return repl_words(words)

    def repl_words(words: list[str]) -> str:
        """Art arda isim kelimelerini tek yer tutucuya çevirir; zamir, kısaltma ve yer tutucuları olduğu gibi bırakır."""
        out, run = [], []

        def flush():
            if run:
                phrase = " ".join(run)
                name = _POSSESSIVE.sub("", phrase)
                out.append(place(name, name) + phrase[len(name):])  # "Dutch's" → "Zorvak's"
                run.clear()
        for w in words:
            if w in used or not _is_name_word(w):
                flush()
                out.append(w)
            else:
                run.append(w)
        flush()
        return " ".join(out)

    return _CAPS.sub(repl, text), mapping


def unprotect(text: str, mapping: dict[str, str]) -> str:
    for ph, target in mapping.items():
        text = re.sub(rf"(?<![\w]){re.escape(ph)}(?![\w])", target, text)
    return text


def build_prompt(text: str, glossary: dict[str, str]) -> str:
    return PROMPT.format(text=text)


def _generate(model: str, prompt: str) -> str:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "keep_alive": "30m",
                       "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["response"]


def translate(text: str, model: str, glossary: dict, cache: dict, known: set[str] | None = None) -> str:
    """known: bilinen isimler (karakterler, daha önce görülenler). Cümle ortasında yeni görülen isimler
    buna eklenir, böylece sonra cümle başında gelseler de korunurlar."""
    known = known if known is not None else set()
    masked, mapping = protect(text, glossary, known)
    for t in mapping.values():  # isimleri öğren (unvanlıysa unvansız hali de: "Bay Morgan" → "Morgan")
        if t not in glossary.values():
            known.add(t)
            first, _, rest = t.partition(" ")
            if first in TITLES.values() and rest:
                known.add(rest)
    key = (model, masked, tuple(sorted(mapping.items())))
    if key not in cache:
        out = _generate(model, build_prompt(masked, glossary)).strip()
        if _REFUSAL.search(out):  # model çeviri yerine "anlayamadım" dedi: çeviri sayma
            raise ValueError("model metni çeviremedi")
        cache[key] = unprotect(out, mapping)
    return cache[key]
