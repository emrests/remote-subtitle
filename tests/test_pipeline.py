import asyncio
import copy

from rsub import pipeline
from rsub.pipeline import Runtime, build_lines, run, stable

P = {"name": "T", "glossary": {}, "speakers": {"Arthur": {"color": "#ff0000", "voice": None}},
     "style": {"nameColor": "#ffd166"}, "source": "x", "region": [0, 0, 1, 1]}


def test_build_lines_colors_and_new_speaker():
    p = copy.deepcopy(P)
    lines, new = build_lines("Arthur: Hi. Sadie: Bye.", p, lambda s: s.upper())
    assert lines == [{"speaker": "Arthur", "color": "#ff0000", "en": "Hi.", "tr": "HI."},
                     {"speaker": "Sadie", "color": "#ffd166", "en": "Bye.", "tr": "BYE."}]
    assert new == ["Sadie"]
    assert "Sadie" not in p["speakers"]  # profil iş parçacığında değiştirilmez; döngü ekler


def test_build_lines_known_speakers_unchanged():
    assert build_lines("Arthur: Hi.", copy.deepcopy(P), str)[1] == []


def test_build_lines_no_speaker_has_no_color():
    assert build_lines("We ride.", copy.deepcopy(P), str)[0] == [{"speaker": None, "color": None, "en": "We ride.", "tr": "We ride."}]


def test_build_lines_empty_clears():
    assert build_lines("", copy.deepcopy(P), str) == ([], [])


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
    monkeypatch.setattr(pipeline, "translate", lambda *a, **k: "Selam.")
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
    monkeypatch.setattr(pipeline, "translate", lambda *a, **k: "Selam.")
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
    monkeypatch.setattr(pipeline, "translate", lambda *a, **k: "Selam.")
    sent = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=sent.append)
    try:
        asyncio.run(asyncio.wait_for(run(rt, interval=0.01), 1.5))
    except TimeoutError:
        pass
    assert [m["lines"] for m in sent][-1] == [] and rt.last_lines == []


def test_run_adds_new_speakers_on_loop(monkeypatch):
    monkeypatch.setattr(pipeline, "target_rect", lambda src: (0, 0, 10, 10))
    monkeypatch.setattr(pipeline, "grab", lambda sct, box: None)
    async def fake_ocr(engine, shot):
        return "Sadie: Hi."
    monkeypatch.setattr(pipeline, "ocr", fake_ocr)
    monkeypatch.setattr(pipeline, "translate", lambda *a, **k: "Selam.")
    saved = []
    monkeypatch.setattr(pipeline.store, "save_profile", saved.append)
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=lambda m: None)
    try:
        asyncio.run(asyncio.wait_for(run(rt, interval=0.01), 0.4))
    except TimeoutError:
        pass
    assert rt.profile["speakers"]["Sadie"] == {"color": None, "voice": None} and saved


def _fake_frame(monkeypatch, text="Hi.", translated="Selam."):
    calls = {"ocr": 0, "translate": 0}
    monkeypatch.setattr(pipeline, "target_rect", lambda src: (0, 0, 10, 10))
    monkeypatch.setattr(pipeline, "grab", lambda sct, box: None)
    async def fake_ocr(engine, shot):
        calls["ocr"] += 1
        from rsub.ocr import OcrText
        out = OcrText(text)
        out.box, out.lines = ((10, 5, 200, 30), 1) if text else (None, 0)
        return out
    def fake_tr(*a, **k):
        calls["translate"] += 1
        return translated
    monkeypatch.setattr(pipeline, "ocr", fake_ocr)
    monkeypatch.setattr(pipeline, "translate", fake_tr)
    return calls


def _run_briefly(rt, seconds=0.4):
    try:
        asyncio.run(asyncio.wait_for(run(rt, interval=0.01), seconds))
    except TimeoutError:
        pass


def test_paused_does_not_read(monkeypatch):
    calls = _fake_frame(monkeypatch)
    sent = []
    rt = Runtime(settings={"model": "m", "running": False}, profile=copy.deepcopy(P), emit=sent.append)
    _run_briefly(rt)
    assert calls["ocr"] == 0 and sent == [] and rt.status["running"] is False


def test_pause_clears_subtitle(monkeypatch):
    _fake_frame(monkeypatch)
    sent = []
    rt = Runtime(settings={"model": "m", "running": False}, profile=copy.deepcopy(P), emit=sent.append)
    rt.last_lines = [{"speaker": None, "color": None, "en": "Hi.", "tr": "Selam."}]
    _run_briefly(rt)
    assert sent == [{"type": "lines", "lines": []}]


def test_model_not_ready_shows_english_without_ollama(monkeypatch):
    calls = _fake_frame(monkeypatch)
    sent = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=sent.append)
    rt.model_ready = False
    _run_briefly(rt)
    assert calls["translate"] == 0
    assert sent[0]["lines"][0]["tr"] == "Hi."
    assert "hazır değil" in rt.status["error"]


def test_paused_still_reports_window(monkeypatch):
    _fake_frame(monkeypatch)
    rt = Runtime(settings={"model": "m", "running": False}, profile=copy.deepcopy(P), emit=lambda m: None)
    _run_briefly(rt)
    assert rt.status["window"] is True


def test_on_frame_reports_rect_and_none_when_paused(monkeypatch):
    _fake_frame(monkeypatch)
    seen = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=lambda m: None)
    rt.on_frame = lambda rect, img=None: seen.append(rect)
    _run_briefly(rt, 0.2)
    assert (0, 0, 10, 10) in seen
    seen.clear()
    rt.settings["running"] = False
    _run_briefly(rt, 0.2)
    assert seen and set(seen) == {None}


def test_on_frame_gets_region_image(monkeypatch):
    _fake_frame(monkeypatch)

    class Shot:
        size, rgb = (2, 1), b"\x00" * 6
    monkeypatch.setattr(pipeline, "grab", lambda sct, box: Shot())
    seen = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=lambda m: None)
    rt.on_frame = lambda rect, img=None: seen.append(img)
    _run_briefly(rt, 0.2)
    assert any(i is not None and i.size == (2, 1) for i in seen)


def _feed(frames):
    s = {"prev": None, "sent": ""}
    return [stable(s, t) for t in frames]


def test_stable_tolerates_I_l_jitter():
    # gerçek RDR2 ölçümü: OCR her karede I/l arasında gidip geliyordu, satır 0,8 sn gecikiyordu
    out = _feed(["I'm freezing.", "l'm freezing.", "I'm freezing.", "l'm freezing."])
    assert out[1] is not None and out[2:] == [None, None]


def test_stable_ignores_trailing_junk_after_sent():
    out = _feed(["Let's try this way.", "Let's try this way.", "Let's try this way.••", "Let's try this way.••"])
    assert out[1] == "Let's try this way." and out[2:] == [None, None]


def test_stable_emits_genuinely_new_line():
    out = _feed(["Come on, compadre.", "Come on, compadre.", "Ain't you a sorry sight?", "Ain't you a sorry sight?"])
    assert out == [None, "Come on, compadre.", None, "Ain't you a sorry sight?"]


def test_new_line_is_covered_before_translation(monkeypatch):
    _fake_frame(monkeypatch, text="Of course.")
    seen = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=lambda m: None)

    def on_frame(rect, img=None):
        seen.append((rt.pending_box, list(rt.last_lines)))
    rt.on_frame = on_frame
    _run_briefly(rt, 0.3)
    first = seen[0]
    assert first[0] is not None and first[1] == []  # ilk karede: kapatılacak yer belli, çeviri henüz yok
    assert seen[-1][0] is None and seen[-1][1]  # çeviri gelince bekleyen kapanış kalkar


def test_default_interval_is_100ms():
    import inspect
    assert inspect.signature(run).parameters["interval"].default == 0.1


def _seq_frame(monkeypatch, seq, translated="Selam."):
    """OCR'ın kare kare döndüreceği (metin, kutu) dizisi; dizi bitince son öğe tekrarlanır."""
    from rsub.ocr import OcrText
    it = iter(seq)
    last = [seq[-1]]
    monkeypatch.setattr(pipeline, "target_rect", lambda src: (0, 0, 1000, 200))
    monkeypatch.setattr(pipeline, "grab", lambda sct, box: None)

    async def fake_ocr(engine, shot):
        text, box = next(it, last[0])
        out = OcrText(text)
        out.box, out.lines = (box, 1) if text else (None, 0)
        return out
    monkeypatch.setattr(pipeline, "ocr", fake_ocr)
    monkeypatch.setattr(pipeline, "translate", lambda *a, **k: translated)


def _record(rt):
    frames = []
    rt.on_frame = lambda rect, img=None: frames.append((rt.pending_box, [l["tr"] for l in rt.last_lines], rt.text_box))
    return frames


B = (100, 50, 400, 40)
LINE_A = "We can't go back the way we came."


def test_one_frame_misread_does_not_blank_translation(monkeypatch):
    seq = [(LINE_A, B)] * 4 + [("We can't go", (100, 50, 180, 40))] + [(LINE_A, B)] * 10  # bir karede yarım okuma
    _seq_frame(monkeypatch, seq)
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=lambda m: None)
    frames = _record(rt)
    _run_briefly(rt, 0.4)
    shown = [i for i, f in enumerate(frames) if f[1]]
    assert shown and all(frames[i][0] is None and frames[i][1] for i in range(shown[0], len(frames)))


def test_single_empty_frame_does_not_clear(monkeypatch):
    seq = [(LINE_A, B)] * 4 + [("", None)] + [(LINE_A, B)] * 10
    _seq_frame(monkeypatch, seq)
    sent = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=sent.append)
    _run_briefly(rt, 0.4)
    assert [m["lines"] for m in sent].count([]) == 0


def test_three_empty_frames_clear(monkeypatch):
    seq = [(LINE_A, B)] * 4 + [("", None)] * 10
    _seq_frame(monkeypatch, seq)
    sent = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=sent.append)
    _run_briefly(rt, 0.4)
    assert sent[-1]["lines"] == []


def test_cover_grows_to_full_line_while_fading_in(monkeypatch):
    small, full = (180, 55, 240, 30), (100, 50, 400, 40)
    seq = [(LINE_A, small), (LINE_A, small), (LINE_A, small), (LINE_A, full)] + [(LINE_A, small)] * 10
    _seq_frame(monkeypatch, seq)
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=lambda m: None)
    frames = _record(rt)
    _run_briefly(rt, 0.4)
    assert frames[-1][2] == full  # yarım okunan kareler kutuyu küçültmez


def test_real_new_line_switches_after_two_frames(monkeypatch):
    seq = [(LINE_A, B)] * 4 + [("Let's try this way instead.", (150, 50, 300, 40))] * 10
    _seq_frame(monkeypatch, seq, translated="X")
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=lambda m: None)
    frames = _record(rt)
    _run_briefly(rt, 0.5)
    assert any(f[0] is not None for f in frames[5:])  # yeni satır boş kutuyla kapatıldı


def test_font_size_fixed_while_line_shown(monkeypatch):
    normal, tall = (100, 50, 400, 39), (100, 50, 400, 120)  # bir karede altındaki ipucu da okundu
    seq = [(LINE_A, normal)] * 4 + [(LINE_A, tall)] + [(LINE_A, normal)] * 10
    _seq_frame(monkeypatch, seq)
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=lambda m: None)
    sizes = []
    rt.on_frame = lambda rect, img=None: sizes.append(rt.text_px)
    _run_briefly(rt, 0.4)
    shown = [s for s in sizes if s]
    assert shown and max(shown) - min(shown) < 1  # yazı boyutu satır boyunca sabit
    assert 38 <= shown[0] <= 42


def test_pending_size_not_inherited_by_next_line(monkeypatch):
    big, small = (100, 50, 400, 80), (100, 50, 400, 39)
    # gösterilen satır A; iki kare yanlış/büyük okuma (bekleyen kapak açılır), sonra A'ya dönülür; sonra yeni satır B
    seq = ([(LINE_A, small)] * 4 + [("Zzz qqq vvv www", big), ("Yyy ppp kkk jjj", big)] + [(LINE_A, small)] * 3
           + [("Totally different words now.", small)] * 8)
    _seq_frame(monkeypatch, seq)
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=lambda m: None)
    seen = []
    rt.on_frame = lambda rect, img=None: seen.append((rt.pending_box, rt.pending_px))
    _run_briefly(rt, 0.6)
    pend_px = [px for box, px in seen if box and box[0] == small]  # B için açılan boş kapak
    assert pend_px and all(px < 45 for px in pend_px)  # iptal edilen büyük kapağın boyutu devralınmaz


def test_garbage_reading_is_not_translated(monkeypatch):
    seq = [("Get t he Cli j 2LIÇJ3", B)] * 6
    _seq_frame(monkeypatch, seq)
    sent = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=sent.append)
    frames = _record(rt)
    _run_briefly(rt, 0.3)
    assert sent == [] and all(f[0] is None for f in frames)  # ne çeviri ne kapak


def test_more_complete_reading_replaces_partial(monkeypatch):
    seq = [("Get to t cliff edg", B)] * 4 + [("Get to the cliff edge.", B)] * 8
    _seq_frame(monkeypatch, seq)
    sent = []
    rt = Runtime(settings={"model": "m"}, profile=copy.deepcopy(P), emit=sent.append)
    _run_briefly(rt, 0.5)
    ens = [m["lines"][0]["en"] for m in sent if m["lines"]]
    assert ens[-1] == "Get to the cliff edge."
