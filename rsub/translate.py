"""Ollama ile İngilizce → Türkçe çeviri, terim listesi ve önbellek."""
import json
import urllib.request

OLLAMA = "http://localhost:11434"
PROMPT = (
    "You are a professional English (en) to Turkish (tr) translator. Your goal is to accurately "
    "convey the meaning and nuances of the original English text while adhering to Turkish grammar, "
    "vocabulary, and cultural sensitivities. Produce only the Turkish translation, without any "
    "additional explanations or commentary. Please translate the following English text into Turkish:"
    "\n\n\n{text}"
)


def build_prompt(text: str, glossary: dict[str, str]) -> str:
    low = text.lower()
    terms = [f"{en} = {tr}" for en, tr in glossary.items() if en and en.lower() in low]
    head = f"Use these fixed translations: {'; '.join(terms)}.\n\n" if terms else ""
    return PROMPT.format(text=head + text)


def _generate(model: str, prompt: str) -> str:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "keep_alive": "30m",
                       "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["response"]


def translate(text: str, model: str, glossary: dict, cache: dict) -> str:
    key = (model, text, tuple(sorted(glossary.items())))
    if key not in cache:
        cache[key] = _generate(model, build_prompt(text, glossary)).strip()
    return cache[key]
