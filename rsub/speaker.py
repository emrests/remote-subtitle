"""OCR metnini "İsim: replik" bloklarına böler."""
import re

# İsim: metnin başında ya da cümle sonundan sonra, büyük harfle başlayan en fazla 3 kelime, ardından ":".
NAME = re.compile(r"""(?:^|(?<=[.!?…"] ))([A-Z][\w'.-]*(?: [A-Z][\w'.-]*){0,2}):\s+""")


def split_speakers(text: str) -> list[tuple[str | None, str]]:
    # "WARNING:" gibi tamamı büyük harfli sistem kelimeleri isim sayılmaz
    hits = [m for m in NAME.finditer(text) if not (len(m.group(1)) > 1 and m.group(1).isupper())]
    out, pos, who = [], 0, None
    for m in hits:
        if chunk := text[pos:m.start()].strip():
            out.append((who, chunk))
        who, pos = m.group(1), m.end()
    if chunk := text[pos:].strip():
        out.append((who, chunk))
    return out
