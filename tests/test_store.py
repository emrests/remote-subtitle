from rsub import store


def test_defaults_when_empty():
    assert store.load_settings() == {"profile": "Varsayılan", "model": "translategemma:12b", "chiakiPath": "", "running": False, "overlay": True, "ps5Host": ""}
    assert store.load_profile("Varsayılan")["region"] == [0.0, 0.7, 1.0, 0.3]


def test_save_and_list_roundtrip():
    p = store.default_profile("RDR2")
    p["glossary"] = {"Arthur": "Arthur"}
    store.save_profile(p)
    assert store.list_profiles() == ["RDR2"] and store.load_profile("RDR2")["glossary"] == {"Arthur": "Arthur"}


def test_load_profile_fills_defaults():
    (store.home() / "profiles").mkdir(parents=True)
    store._path("Eski").write_text('{"name":"Eski","style":{"size":30}}', encoding="utf-8")
    p = store.load_profile("Eski")
    assert p["style"]["size"] == 30 and p["style"]["nameColor"] == "#ffd166" and p["speakers"] == {}


def test_corrupt_profile_falls_back():
    (store.home() / "profiles").mkdir(parents=True)
    store._path("Bozuk").write_text("{not json", encoding="utf-8")
    assert store.load_profile("Bozuk")["name"] == "Bozuk"


def test_profile_name_with_illegal_chars():
    store.save_profile(store.default_profile("Spider-Man: 2/b"))
    assert store.list_profiles() == ["Spider-Man: 2/b"]


def test_copy_and_delete():
    store.save_profile(store.default_profile("A"))
    store.copy_profile("A", "B")
    store.delete_profile("A")
    assert store.list_profiles() == ["B"]


def test_settings_roundtrip():
    store.save_settings({"profile": "RDR2", "model": "gemma3:12b", "chiakiPath": "C:/x.exe"})
    assert store.load_settings()["model"] == "gemma3:12b"


def test_wrong_types_fall_back_to_defaults():
    (store.home() / "profiles").mkdir(parents=True)
    store._path("X").write_text('{"name":"X","style":"x","region":[0,0],"speakers":{"Arthur":"#f00","Sadie":{}},'
                                '"glossary":[1]}', encoding="utf-8")
    p = store.load_profile("X")
    assert p["style"] == store.DEFAULT_STYLE and p["region"] == [0.0, 0.7, 1.0, 0.3] and p["glossary"] == {}
    assert p["speakers"] == {"Sadie": {"color": None, "voice": None}}


def test_settings_wrong_type_falls_back():
    store.home().mkdir(parents=True, exist_ok=True)
    (store.home() / "settings.json").write_text("[1,2]", encoding="utf-8")
    assert store.load_settings()["model"] == "translategemma:12b"


def test_failed_write_keeps_old_file(monkeypatch):
    store.save_profile(store.default_profile("A"))
    def boom(*a):
        raise OSError("disk full")
    monkeypatch.setattr(store.os, "replace", boom)
    p = store.default_profile("A"); p["glossary"] = {"x": "y"}
    try:
        store.save_profile(p)
    except OSError:
        pass
    assert store.load_profile("A")["glossary"] == {} and store.list_profiles() == ["A"]


def test_case_only_different_names_do_not_collide():
    store.save_profile(store.default_profile("aaa"))
    store.save_profile(store.default_profile("aaG"))
    assert store.list_profiles() == ["aaG", "aaa"]


def test_very_long_profile_name():
    name = "x" * 300
    store.save_profile(store.default_profile(name))
    assert store.list_profiles() == [name]


def test_first_run_flag():
    assert store.settings_exist() is False
    store.save_settings(store.load_settings())
    assert store.settings_exist() is True


def test_speaker_color_option_defaults_off_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("RSUB_HOME", str(tmp_path))
    assert store.default_profile("A")["speakerColor"] is False
    p = store.default_profile("A"); p["speakerColor"] = True; store.save_profile(p)
    assert store.load_profile("A")["speakerColor"] is True
