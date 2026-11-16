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
