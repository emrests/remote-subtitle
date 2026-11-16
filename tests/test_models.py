from rsub.models import model_infos, recommend


def test_recommend():
    assert recommend(16303) == "translategemma:12b"
    assert recommend(24576) == "translategemma:27b"
    assert recommend(6144) == "translategemma:4b"
    assert recommend(None) == "translategemma:4b"


def test_model_infos_marks_fit():
    infos = model_infos(16303)
    assert [i["fits"] for i in infos] == [False, True, True, True]
    assert [i["id"] for i in infos if i["recommended"]] == ["translategemma:12b"]


def test_ollama_up_survives_non_ollama_server(monkeypatch):
    import http.client
    from rsub import models
    def bad(path, timeout):
        raise http.client.BadStatusLine("x")
    monkeypatch.setattr(models, "_get", bad)
    assert models.ollama_up() is False and models.installed() == set()


def test_start_ollama_without_install(monkeypatch, tmp_path):
    from rsub import models
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    assert models.start_ollama() is False


def test_start_ollama_launches_serve(monkeypatch, tmp_path):
    from rsub import models
    exe = tmp_path / "Programs" / "Ollama" / "ollama.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    calls = []
    monkeypatch.setattr(models.subprocess, "Popen", lambda args, **k: calls.append(args))
    assert models.start_ollama() is True and calls == [[str(exe), "serve"]]
