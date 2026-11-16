import asyncio
import copy

from rsub import pipeline
from rsub.pipeline import Runtime, build_lines, run, stable

P = {"name": "T", "glossary": {}, "speakers": {"Arthur": {"color": "#ff0000", "voice": None}},
     "style": {"nameColor": "#ffd166"}, "source": "x", "region": [0, 0, 1, 1]}


def test_build_lines_colors_and_new_speaker():
    p = copy.deepcopy(P)
    lines, changed = build_lines("Arthur: Hi. Sadie: Bye.", p, lambda s: s.upper())
    assert lines == [{"speaker": "Arthur", "color": "#ff0000", "en": "Hi.", "tr": "HI."},
                     {"speaker": "Sadie", "color": "#ffd166", "en": "Bye.", "tr": "BYE."}]
    assert changed is True and p["speakers"]["Sadie"] == {"color": None, "voice": None}


def test_build_lines_known_speakers_unchanged():
    assert build_lines("Arthur: Hi.", copy.deepcopy(P), str)[1] is False


def test_build_lines_no_speaker_has_no_color():
    assert build_lines("We ride.", copy.deepcopy(P), str)[0] == [{"speaker": None, "color": None, "en": "We ride.", "tr": "We ride."}]


def test_build_lines_empty_clears():
    assert build_lines("", copy.deepcopy(P), str) == ([], False)


def test_translate_failure_falls_back_to_english():
    def boom(s):
        raise OSError("ollama down")
    lines, _ = build_lines("We ride.", copy.deepcopy(P), boom)
    assert lines[0]["tr"] == "We ride."


def test_stable_sequence():
    s = {"prev": None, "sent": ""}
    assert [stable(s, t) for t in ["", "Hel", "Hello", "Hello", "Hello", "", ""]] == [None, None, None, "Hello", None, None, ""]


def test_run_survives_missing_window(monkeypatch):
    monkeypatch.setattr(pipeline, "target_rect", lambda src: None)
    sent = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=sent.append)
    try:
        asyncio.run(asyncio.wait_for(run(rt), 1.2))
    except TimeoutError:
        pass
    assert rt.status["window"] is False and sent == []


def test_run_emits_translated_lines(monkeypatch):
    monkeypatch.setattr(pipeline, "target_rect", lambda src: (0, 0, 10, 10))
    monkeypatch.setattr(pipeline, "grab", lambda sct, box: None)
    async def fake_ocr(engine, shot):
        return "Arthur: Hi."
    monkeypatch.setattr(pipeline, "ocr", fake_ocr)
    monkeypatch.setattr(pipeline, "translate", lambda text, model, glossary, cache: "Selam.")
    sent = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=sent.append)
    try:
        asyncio.run(asyncio.wait_for(run(rt, interval=0.01), 0.5))
    except TimeoutError:
        pass
    assert sent == [{"type": "lines", "lines": [{"speaker": "Arthur", "color": "#ff0000", "en": "Hi.", "tr": "Selam."}]}]
    assert rt.status["window"] is True and rt.status["last"]["translate"] >= 0 and rt.status["error"] is None


def test_run_survives_unexpected_error(monkeypatch):
    calls = {"n": 0}
    def flaky(sct, box):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
    monkeypatch.setattr(pipeline, "target_rect", lambda src: (0, 0, 10, 10))
    monkeypatch.setattr(pipeline, "grab", flaky)
    async def fake_ocr(engine, shot):
        return "Hi."
    monkeypatch.setattr(pipeline, "ocr", fake_ocr)
    monkeypatch.setattr(pipeline, "translate", lambda *a: "Selam.")
    monkeypatch.setattr(pipeline, "ERROR_PAUSE", 0.05)
    sent = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=sent.append)
    try:
        asyncio.run(asyncio.wait_for(run(rt, interval=0.01), 0.6))
    except TimeoutError:
        pass
    assert sent and sent[0]["lines"][0]["tr"] == "Selam."


def test_lost_window_clears_subtitle(monkeypatch):
    rects = iter([(0, 0, 10, 10)] * 3)
    monkeypatch.setattr(pipeline, "target_rect", lambda src: next(rects, None))
    monkeypatch.setattr(pipeline, "grab", lambda sct, box: None)
    async def fake_ocr(engine, shot):
        return "Hi."
    monkeypatch.setattr(pipeline, "ocr", fake_ocr)
    monkeypatch.setattr(pipeline, "translate", lambda *a: "Selam.")
    sent = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=sent.append)
    try:
        asyncio.run(asyncio.wait_for(run(rt, interval=0.01), 1.5))
    except TimeoutError:
        pass
    assert [m["lines"] for m in sent][-1] == [] and rt.last_lines == []
