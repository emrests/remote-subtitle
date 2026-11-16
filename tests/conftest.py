import pytest


@pytest.fixture(autouse=True)
def rsub_home(tmp_path, monkeypatch):
    monkeypatch.setenv("RSUB_HOME", str(tmp_path))
    return tmp_path
