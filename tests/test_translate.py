from rsub import translate as translate_mod
from rsub.translate import build_prompt, translate


def test_prompt_contains_text_and_only_relevant_terms():
    p = build_prompt("Arthur rides to Valentine.", {"Arthur": "Arthur", "Valentine": "Valentine", "Dutch": "Dutch"})
    assert p.endswith("Arthur rides to Valentine.")
    assert "Valentine = Valentine" in p and "Dutch" not in p


def test_prompt_term_match_is_case_insensitive():
    assert "Dead Eye = Ölü Göz" in build_prompt("use DEAD EYE now", {"Dead Eye": "Ölü Göz"})


def test_prompt_without_glossary_is_base_prompt():
    assert "=" not in build_prompt("Hi.", {})


def test_translate_uses_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(translate_mod, "_generate", lambda model, prompt: calls.append(1) or " Selam. ")
    cache = {}
    assert translate("Hi.", "m", {}, cache) == "Selam."
    translate("Hi.", "m", {}, cache)
    assert len(calls) == 1
