from rsub import ocr


def test_latin_language_counts_as_ready(monkeypatch):
    monkeypatch.setattr(ocr, "_languages", lambda: ["tr"])
    assert ocr.ocr_language() == "tr"


def test_english_preferred(monkeypatch):
    monkeypatch.setattr(ocr, "_languages", lambda: ["tr", "en-US"])
    assert ocr.ocr_language() == "en-US"


def test_non_latin_only_is_not_ready(monkeypatch):
    monkeypatch.setattr(ocr, "_languages", lambda: ["ja", "zh-Hans-CN"])
    assert ocr.ocr_language() is None


def test_real_machine_has_some_language():
    assert ocr.ocr_language() is not None
