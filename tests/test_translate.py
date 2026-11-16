from rsub import translate as translate_mod
from rsub.translate import build_prompt, translate


def test_prompt_has_no_instruction_text():
    # TranslateGemma talimatı da çevirip ekrana basıyordu ("Bu sabit çevirileri kullanın: Dutch = Hollandaca")
    assert "Use these" not in build_prompt("Have you seen Dutch anywhere?", {"Dutch": "Dutch"})


def test_translate_uses_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(translate_mod, "_generate", lambda model, prompt: calls.append(1) or " Selam. ")
    cache = {}
    assert translate("Hi.", "m", {}, cache) == "Selam."
    translate("Hi.", "m", {}, cache)
    assert len(calls) == 1


def test_ollama_address_is_ipv4_literal():
    # Windows'ta "localhost" önce ::1 denenir; Ollama yalnız 127.0.0.1'de dinlediğinden her istek ~2 sn gecikiyordu
    assert translate_mod.OLLAMA == "http://127.0.0.1:11434"


from rsub.translate import protect, unprotect


def test_mid_sentence_name_is_protected():
    masked, m = protect("Have you seen Dutch anywhere?", {}, set())
    assert "Dutch" not in masked and list(m.values()) == ["Dutch"]


def test_sentence_start_word_not_protected_unless_known():
    masked, m = protect("Dutch says we leave.", {}, set())
    assert m == {}
    masked, m = protect("Dutch says we leave.", {}, {"Dutch"})
    assert list(m.values()) == ["Dutch"]


def test_pronoun_I_and_all_caps_not_protected():
    assert protect("Yes, I think I'm fine, OK?", {}, set())[1] == {}
    assert protect("Look out, WARNING ahead.", {}, set())[1] == {}


def test_multiword_name_single_placeholder():
    masked, m = protect("We ride to Saint Denis tonight.", {}, set())
    assert list(m.values()) == ["Saint Denis"]


def test_glossary_term_restored_as_target():
    masked, m = protect("Use Dead Eye when they draw.", {"Dead Eye": "Ölü Göz"}, set())
    assert "Ölü Göz" in m.values() and "Dead Eye" not in masked


def test_unprotect_keeps_turkish_suffix():
    masked, m = protect("I owe Dutch my life.", {}, set())
    ph = next(iter(m))
    assert unprotect(f"{ph}'a hayatımı borçluyum.", m) == "Dutch'a hayatımı borçluyum."


def test_placeholder_vowel_matches_name():
    _, m = protect("Have you met Sadie today?", {}, set())  # son ünlü e → ince ünlülü yer tutucu
    ph = next(iter(m))
    assert [c for c in ph.lower() if c in "aeıioöuü"][-1] in "ei"


def test_translate_keeps_names(monkeypatch):
    seen = []
    def echo(model, prompt):  # model maskeli metni olduğu gibi döndürsün
        seen.append(prompt)
        return prompt.rsplit("\n", 1)[-1]
    monkeypatch.setattr(translate_mod, "_generate", echo)
    out = translate("Have you seen Dutch anywhere?", "m", {}, {})
    assert "Dutch" not in seen[0] and "Dutch" in out


def test_glossary_placeholder_follows_turkish_target_vowel():
    _, m = protect("Use Dead Eye now.", {"Dead Eye": "Ölü Göz"}, set())  # Göz → ö: ek "ü" olmalı
    ph = next(p for p, t in m.items() if t == "Ölü Göz")
    assert [c for c in ph.lower() if c in "aeıioöuü"][-1] in "öü"


def test_title_and_name_are_one_unit():
    masked, m = protect("Now, Mr. Morgan and I,", {}, set())
    assert list(m.values()) == ["Bay Morgan"] and "Mr" not in masked and "Morgan" not in masked


def test_titles_turkish():
    assert list(protect("Ask Mrs. Adler about it.", {}, set())[1].values()) == ["Bayan Adler"]
    assert list(protect("Miss Grimshaw won't like this.", {}, set())[1].values()) == ["Bayan Grimshaw"]
    assert list(protect("Take him to Dr. Joseph now.", {}, set())[1].values()) == ["Dr. Joseph"]


def test_title_at_sentence_start_is_protected():
    assert list(protect("Mr. Morgan, wait for me.", {}, set())[1].values()) == ["Bay Morgan"]


def test_name_after_title_becomes_known(monkeypatch):
    monkeypatch.setattr(translate_mod, "_generate", lambda model, prompt: prompt.rsplit("\n", 1)[-1])
    known = set()
    translate("Now, Mr. Morgan and I,", "m", {}, {}, known=known)
    assert "Morgan" in known
    assert list(protect("Morgan, are you coming?", {}, known)[1].values()) == ["Morgan"]


def test_model_refusal_is_not_a_translation(monkeypatch):
    import pytest
    monkeypatch.setattr(translate_mod, "_generate", lambda m, p: "Üzgünüm, ancak bu metnin anlamını çözemiyorum. Lütfen daha fazla bağlam sağlayabilir misiniz?")
    with pytest.raises(ValueError):
        translate("e!jîî", "m", {}, {})


def test_word_after_leading_number_is_sentence_start():
    assert protect("47 Get to the cliff edge", {}, set())[1] == {}


def test_unprotect_suffix_without_apostrophe():
    assert unprotect("Tavrini, kayalıkların kenarına yönlendirin.", {"Tavrin": "Get"}) == "Get'i, kayalıkların kenarına yönlendirin."
    assert unprotect("Tavrin'i gördüm.", {"Tavrin": "Sadie"}) == "Sadie'i gördüm."


def test_model_commentary_in_parentheses_removed(monkeypatch):
    monkeypatch.setattr(translate_mod, "_generate", lambda m, p: "Com? (Bu soruya bir cevap gerekiyor.)")
    assert translate("Com?", "m", {}, {}) == "Com?"
    monkeypatch.setattr(translate_mod, "_generate", lambda m, p: "Tamam (sanırım).")
    assert translate("Okay (I guess).", "m", {}, {}) == "Tamam (sanırım)."  # orijinalde parantez varsa kalır
