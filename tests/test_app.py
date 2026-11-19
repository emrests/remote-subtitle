import websockets

from rsub import app


def test_ask_show_ignores_bad_handshake(monkeypatch):
    import websockets.sync.client as client

    def bad(*a, **k):
        raise websockets.InvalidHandshake("not a websocket server")
    monkeypatch.setattr(client, "connect", bad)
    app.ask_show(1)  # hata fırlatmamalı


def test_error_page_escapes_and_explains():
    html = app.error_page("<b>port 8765 kullanımda</b>")
    assert "&lt;b&gt;port 8765 kullanımda&lt;/b&gt;" in html and "<b>port" not in html
    assert "başlatılamadı" in html


def test_close_choice_maps_buttons(monkeypatch):
    import ctypes
    for code, want in ((6, "ollama"), (7, "app"), (2, None)):
        monkeypatch.setattr(ctypes.windll.user32, "MessageBoxW", lambda *a, c=code: c)
        assert app.ask_close() == want


def test_shutdown_stops_ollama_only_when_asked(monkeypatch):
    from rsub import models
    calls = []
    monkeypatch.setattr(app, "unload_model", lambda: calls.append("unload"))
    monkeypatch.setattr(models.subprocess, "run", lambda cmd, **k: calls.append(cmd[-1]))
    app.shutdown("app")
    assert calls == ["unload"]  # yalnız uygulama: Ollama'ya dokunulmaz
    calls.clear()
    app.shutdown("ollama")
    assert calls == ["unload", "ollama app.exe", "ollama.exe"]  # önce tepsi uygulaması
