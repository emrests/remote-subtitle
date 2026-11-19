"""Sesli dublaj: kuyruk kuralı, bir kez klonlama, örnek toplama koşulları (sahte işçi ve çalma ile)."""
import json
import wave

from rsub import dub, store, web


class FakeProc:
    def __init__(self):
        self.sent = []
        self.stdin = self
        self.stdout = iter(())  # okuyucu iş parçacığı hemen biter; yanıtlar elle verilir

    def write(self, s):
        self.sent.append(json.loads(s))

    def flush(self):
        pass

    def poll(self):
        return None

    def kill(self):
        pass


def _dubber(tmp_path):
    proc = FakeProc()
    played, events = [], []
    d = dub.Dubber(lambda wav, job: None, events.append, spawn=lambda: proc, play=played.append)
    d._read = lambda p: None
    return d, proc, played, events


def _wav(path, seconds=0.2):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000)
        w.writeframes(b"\0\0" * int(8000 * seconds))
    return str(path)


def test_queue_keeps_one_pending_and_newest_wins(tmp_path):
    d, proc, played, _ = _dubber(tmp_path)
    d.say("bir", None)
    d.say("iki", None)
    d.say("üç", None)  # "iki" beklerken geldi: onun yerine geçer
    says = [m for m in proc.sent if m["op"] == "say"]
    assert [m["text"] for m in says] == ["bir"]
    d.handle({"id": says[0]["id"], "wav": _wav(tmp_path / "a.wav"), "ms": 900})
    says = [m for m in proc.sent if m["op"] == "say"]
    assert [m["text"] for m in says] == ["bir", "üç"] and d.status["lastMs"] == 900


def test_own_playback_not_sampled(tmp_path):
    d, proc, _, _ = _dubber(tmp_path)
    d.played = [(100.0, 103.0)]
    d.clip("Lucia", 102.0, 105.0, "x.pt")  # kendi dublajımız çalarken: alınmaz
    d.clip("Lucia", 104.0, 106.0, "x.pt")
    assert [m["start"] for m in proc.sent if m["op"] == "clip"] == [104.0]


def _app(monkeypatch, tmp_path):
    monkeypatch.setattr(dub, "available", lambda: True)
    a = web.App(web.WEB_DIR, None)
    a.dub, proc, played, events = _dubber(tmp_path)
    a.dub.on_event = a._dub_event
    a.rt.settings["running"] = True
    a.rt.profile["dub"] = {"on": True, "pc": True, "tv": False, "volume": 1.0}
    a.rt.profile["speakers"] = {"Lucia": {"color": None, "voice": None}, "Jason": {"color": None, "voice": None}}
    return a, proc


def test_sample_only_for_voiceless_single_speaker_then_cloned_once(monkeypatch, tmp_path):
    a, proc = _app(monkeypatch, tmp_path)
    L = lambda sp: [{"speaker": sp, "color": None, "en": "x", "tr": "Selam."}]
    a.dub_gone(L("Lucia"), 1.0, 3.0)
    a.dub_gone(L(None), 3.0, 4.0)  # konuşmacısız: alınmaz
    a.dub_gone(L("Lucia") + L("Jason"), 4.0, 6.0)  # iki konuşmacı: alınmaz
    clips = [m for m in proc.sent if m["op"] == "clip"]
    assert [c["speaker"] for c in clips] == ["Lucia"]
    out = tmp_path / "lucia.pt"
    out.write_bytes(b"x")
    a.dub.handle({"cloned": "Lucia", "out": str(out)})
    assert a.rt.profile["speakers"]["Lucia"]["voice"] == str(out)
    assert store.load_profile(a.rt.profile["name"])["speakers"]["Lucia"]["voice"] == str(out)  # profilde kalıcı
    a.dub_gone(L("Lucia"), 7.0, 9.0)  # sesi var: bir daha örnek alınmaz
    assert len([m for m in proc.sent if m["op"] == "clip"]) == 1
    a.dub_lines(L("Lucia"))
    say = [m for m in proc.sent if m["op"] == "say"][-1]
    assert say["conds"] == str(out) and say["text"] == "Selam."


def test_dub_off_does_nothing(monkeypatch, tmp_path):
    a, proc = _app(monkeypatch, tmp_path)
    a.rt.profile["dub"]["on"] = False
    a.dub_lines([{"speaker": "Lucia", "color": None, "en": "x", "tr": "Selam."}])
    a.dub_gone([{"speaker": "Lucia", "color": None, "en": "x", "tr": "Selam."}], 1.0, 2.0)
    assert [m for m in proc.sent if m["op"] in ("say", "clip")] == []


def test_app_works_without_dub_env(monkeypatch):
    monkeypatch.setattr(dub, "available", lambda: False)
    a = web.App(web.WEB_DIR, None)
    a.rt.settings["running"] = True
    a.rt.profile["dub"]["on"] = True
    a.dub_lines([{"speaker": None, "color": None, "en": "x", "tr": "Selam."}])  # çökmez
    assert a.status()["dub"] == {"available": False}
