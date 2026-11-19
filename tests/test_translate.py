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
    assert translate_mod.protect("Yes, I think I'm fine, OK?", {}, set())[1] == {}
    assert translate_mod.protect("Look out, WARNING ahead.", {}, set())[1] == {}


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
    for answer in ["Üzgünüm, ancak bu metnin anlamını çözemiyorum. Lütfen daha fazla bağlam sağlayabilir misiniz?",
                   '"for" kelimesinin Türkçe\'ye çevirisi bağlama göre değişir. Lütfen çevrilecek metni sağlayın.',
                   "Elbette, çevirebilirim. Lütfen metni gönderin."]:
        monkeypatch.setattr(translate_mod, "_generate", lambda m, p, a=answer: a)
        assert translate("e!jîî", "m", {}, {}) == ""  # açıklama gösterilmez
    monkeypatch.setattr(translate_mod, "_generate", lambda m, p: "Lütfen, kapıyı kapat.")
    assert translate("Please, close the door.", "m", {}, {}) == "Lütfen, kapıyı kapat."  # sıradan "lütfen" geçer


def test_word_after_leading_number_is_sentence_start():
    assert translate_mod.protect("47 Get to the cliff edge", {}, set())[1] == {}


def test_unprotect_suffix_without_apostrophe():
    assert unprotect("Tavrini, kayalıkların kenarına yönlendirin.", {"Tavrin": "Get"}) == "Get'i, kayalıkların kenarına yönlendirin."
    assert unprotect("Tavrin'i gördüm.", {"Tavrin": "Sadie"}) == "Sadie'i gördüm."


def test_model_commentary_in_parentheses_removed(monkeypatch):
    monkeypatch.setattr(translate_mod, "_generate", lambda m, p: "Com? (Bu soruya bir cevap gerekiyor.)")
    assert translate("Com?", "m", {}, {}) == "Com?"
    monkeypatch.setattr(translate_mod, "_generate", lambda m, p: "Tamam (sanırım).")
    assert translate("Okay (I guess).", "m", {}, {}) == "Tamam (sanırım)."  # orijinalde parantez varsa kalır


def test_game_context_goes_into_prompt():
    # ölçüm: bağlamsız "ride out" → "bisikletlerimizle", Vahşi Batı bağlamıyla → "atlarımızla"
    p = build_prompt("We ride out.", {}, "1899 Wild West, outlaws on horseback")
    assert "Context: 1899 Wild West, outlaws on horseback" in p and p.endswith("We ride out.")
    assert "Context" not in build_prompt("We ride out.", {})


def test_context_change_is_not_served_from_cache(monkeypatch):
    prompts = []
    monkeypatch.setattr(translate_mod, "_generate", lambda model, prompt: prompts.append(prompt) or "x")
    cache = {}
    translate("Ride.", "m", {}, cache, context="")
    translate("Ride.", "m", {}, cache, context="Wild West")
    assert len(prompts) == 2 and "Wild West" in prompts[1]


def test_interjection_mid_sentence_not_protected():
    assert translate_mod.protect("You Okay, miss?", {}, set())[1] == {}
    assert translate_mod.protect("Just follow me, Okay?", {}, set())[1] == {}


def test_model_quotes_removed(monkeypatch):
    monkeypatch.setattr(translate_mod, "_generate", lambda m, p: '"Sen mi çaldın?"')
    assert translate("You stole it?", "m", {}, {}) == "Sen mi çaldın?"
    monkeypatch.setattr(translate_mod, "_generate", lambda m, p: '"Merhaba"')
    assert translate('"Hello"', "m", {}, {}) == '"Merhaba"'  # orijinalde tırnak varsa kalır


def test_model_alternatives_cut_to_first(monkeypatch):
    monkeypatch.setattr(translate_mod, "_generate", lambda m, p: "İyi misin, güzelim? / Bir şey var mı, hatun?")
    assert translate("You okay, miss?", "m", {}, {}) == "İyi misin, güzelim?"
    monkeypatch.setattr(translate_mod, "_generate", lambda m, p: '"Sus lan, aptal herif!" veya "Kapa çeneni, salak!"')
    assert translate("Shut up, you dumb fuck!", "m", {}, {}) == "Sus lan, aptal herif!"


def test_common_words_mid_sentence_not_names():
    assert translate_mod.protect("You wanna Win in that game.", {}, set())[1] == {}
    assert translate_mod.protect("Yeah, well, She's a broker.", {}, set())[1] == {}
    assert list(translate_mod.protect("You know Mark, right?", {}, set())[1].values()) == ["Mark"]
    assert list(translate_mod.protect("Tell Will to come.", {}, {"Will"})[1].values()) == ["Will"]  # bilinen karakter


def test_context_dictionary_keeps_only_terms_in_text():
    ctx = ("Crime story. Slang meanings: homie/dawg = kanka; bread/paper = para; cops/pigs = aynasızlar. "
           "Profanity: fuck = siktir; bitch (to a woman) = kaltak. Translate faithfully")
    rc = translate_mod.relevant_context
    assert rc(ctx, "Go to bed?") == "Crime story. Translate faithfully"
    assert rc(ctx, "Nice paperwork.") == "Crime story. Translate faithfully"  # kelime içinde eşleşmez
    assert rc(ctx, "The pigs are fucking here, bitch.") == (
        "Crime story. Slang meanings: cops/pigs = aynasızlar. Profanity: fuck = siktir; bitch (to a woman) = kaltak. "
        "Translate faithfully")


def test_unload_sends_keep_alive_zero(monkeypatch):
    import json
    sent = []

    class R:
        def close(self): pass
    monkeypatch.setattr(translate_mod.urllib.request, "urlopen", lambda req, timeout: sent.append(json.loads(req.data)) or R())
    translate_mod.unload("translategemma:12b")
    assert sent == [{"model": "translategemma:12b", "keep_alive": 0}]

    def down(req, timeout): raise OSError("kapalı")
    monkeypatch.setattr(translate_mod.urllib.request, "urlopen", down)
    translate_mod.unload("m")  # Ollama kapalıyken hata vermez


def test_profile_context_parts_and_only_mentioned_slang():
    p = {"context": "Crime story in Leonida.", "tone": "Street slang, do not censor",
         "slang": [{"en": "cops/pigs", "tr": "aynasızlar", "note": ""}, {"en": "fucking", "tr": "lan", "note": "as an intensifier"},
                   {"en": "bread", "tr": "para", "note": ""}]}
    pc = translate_mod.profile_context
    assert pc(p, "Go to bed?") == "Crime story in Leonida. Street slang, do not censor"
    assert pc(p, "The fucking pigs!") == ("Crime story in Leonida. Street slang, do not censor. "
                                         "Slang meanings: cops/pigs = aynasızlar; fucking (as an intensifier) = lan")
    assert pc({}, "x") == ""
