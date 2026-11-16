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
