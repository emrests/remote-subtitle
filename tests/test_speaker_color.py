from rsub.ocr import mark_speaker

# Ölçüm: PS5 RDR2 karesi, kelime başına yazı parlaklığı (95. yüzdelik)


def test_dim_name_gets_colon():
    words = ["Arthur", "An", "old", "mining", "town,"]
    assert mark_speaker(words, [88, 167, 167, 166, 167]) == ["Arthur:", "An", "old", "mining", "town,"]


def test_name_vs_addressed_name():
    # Dutch konuşuyor, Arthur'a sesleniyor: yalnız renk farklı olan isim konuşmacı
    assert mark_speaker(["Dutch", "Arthur!", "Any", "luck?"], [88, 170, 166, 166]) == ["Dutch:", "Arthur!", "Any", "luck?"]


def test_two_word_name():
    assert mark_speaker(["Uncle", "Bob", "Hey", "there"], [90, 92, 170, 168]) == ["Uncle", "Bob:", "Hey", "there"]


def test_same_color_unchanged():
    words = ["We", "need", "to", "move."]
    assert mark_speaker(words, [170, 168, 167, 169]) == words


def test_lowercase_or_single_word_unchanged():
    assert mark_speaker(["and", "then", "go"], [88, 170, 170]) == ["and", "then", "go"]
    assert mark_speaker(["Arthur"], [88]) == ["Arthur"]


def test_existing_colon_unchanged():
    assert mark_speaker(["Arthur:", "Go"], [88, 170]) == ["Arthur:", "Go"]


def test_brighter_colored_name_also_counts():
    # bazı oyunlarda isim beyaz, replik gri
    assert mark_speaker(["Sadie", "Come", "on"], [240, 160, 162]) == ["Sadie:", "Come", "on"]
