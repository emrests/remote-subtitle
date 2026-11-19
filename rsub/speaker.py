"""OCR metnini "İsim: replik" bloklarına böler."""
import re

# Oyunların bilgi etiketleri; isim gibi görünür ama konuşmacı değildir
NOT_NAMES = {"Note", "Tip", "Hint", "Objective", "Warning", "Time", "Location", "Reward", "Mission", "Goal", "Bonus", "Tutorial"}
# İsim: metnin başında ya da cümle sonundan sonra, büyük harfle başlayan en fazla 3 kelime, ardından ":".
NAME = re.compile(r"""(?:^|(?<=[.!?…"] ))([A-Z][\w'.-]*(?: [A-Z][\w'.-]*){0,2}):\s+""")


def split_speakers(text: str, known=()) -> list[tuple[str | None, str]]:
    """known: bilinen konuşmacılar. Başta bilinen isimden sonra ":" yerine OCR'ın okuduğu "." ya da ".y" gibi
    bozukluk varsa ":" sayılır ("Stranger.y It's" → "Stranger: It's")."""
    for name in known:
        if re.match(rf"{re.escape(name)}[.,;]\S?\s", text):
            text = re.sub(rf"^{re.escape(name)}[.,;]\S?\s+", name + ": ", text)
            break
        # bilinen isimden önce cümle sonu olmayan parça: silinmekte olan yazının OCR kalıntısı (":nazi wire Stranger: ...")
        m = re.search(rf"(?<!\w){re.escape(name)}:\s", text)
        if m and m.start() and text[:m.start()].rstrip()[-1:] not in ".!?…\"”":
            text = text[m.start():]
            break
    # "WARNING:" gibi tamamı büyük harfli sistem kelimeleri isim sayılmaz
    hits = [m for m in NAME.finditer(text)
            if not (len(m.group(1)) > 1 and m.group(1).isupper()) and m.group(1) not in NOT_NAMES]
    out, pos, who = [], 0, None
    for m in hits:
        if chunk := text[pos:m.start()].strip():
            out.append((who, chunk))
        who, pos = m.group(1), m.end()
    if chunk := text[pos:].strip():
        out.append((who, chunk))
    return out
