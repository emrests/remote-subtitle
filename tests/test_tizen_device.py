import pytest

from rsub import tizen_device as td


class FakeSdb:
    """sdb çıktıları: dün evdeki TV'den alınan biçimler."""

    def __init__(self, install_out="install completed"):
        self.calls, self.install_out = [], install_out

    def __call__(self, args, timeout=60):
        self.calls.append(args)
        if args[0] == "connect":
            return f"connecting to {args[1]}:26101 ...\nconnected to {args[1]}:26101\n"
        if args[0] == "devices":
            return "List of devices attached \n192.168.68.111:26101\tdevice    \tQE75QN800DTXTK\n"
        if args[-2:] == ["0", "getduid"]:
            return "CPCGVGAG2CWJK\n"
        if "push" in args:
            return "1 file(s) pushed. 0 file(s) skipped."
        if "appinstall" in args or "vd_appinstall" in args:
            return self.install_out
        return ""


def test_info_reads_model_and_duid(monkeypatch):
    fake = FakeSdb()
    monkeypatch.setattr(td, "run", fake)
    assert td.info("192.168.68.111") == {"ip": "192.168.68.111", "model": "QE75QN800DTXTK", "duid": "CPCGVGAG2CWJK"}


def test_permit_pushes_profile_to_developer_home(monkeypatch):
    fake = FakeSdb()
    monkeypatch.setattr(td, "run", fake)
    td.permit("1.2.3.4", b"<Profile/>")
    push = [c for c in fake.calls if "push" in c][0]
    assert push[:3] == ["-s", "1.2.3.4:26101", "push"] and push[-1] == "/home/developer/device-profile.xml"


def test_install_pushes_then_appinstall(monkeypatch):
    fake = FakeSdb("spend time for wascmd is [1200]ms\ninstall completed\n")
    monkeypatch.setattr(td, "run", fake)
    td.install("1.2.3.4", b"PK")
    inst = [c for c in fake.calls if "vd_appinstall" in c][0]
    assert inst[-4:] == ["0", "vd_appinstall", "RmSubTvApp", "/home/owner/share/tmp/sdk_tools/tmp/RmSubTvApp.wgt"]


def test_install_accepts_2024_tv_output(monkeypatch):
    monkeypatch.setattr(td, "run", FakeSdb("__return_cb req_id[1] pkg_type[wgt] pkgid[RmSubTvApp] key[end] val[ok]"))
    td.install("1.2.3.4", b"PK")


def test_permit_ignores_refused_path(monkeypatch):
    monkeypatch.setattr(td, "run", lambda args, timeout=60: "error: failed to close '/home/developer/device-profile.xml': You cannot push files to this path.")
    td.permit("1.2.3.4", b"<Profile/>")


def test_install_falls_back_to_plain_appinstall(monkeypatch):
    fake = FakeSdb()
    outs = iter(["command not found", "install completed"])
    def run(args, timeout=60):
        if "appinstall" in args or "vd_appinstall" in args:
            fake.calls.append(args)
            return next(outs)
        return fake(args, timeout)
    monkeypatch.setattr(td, "run", run)
    td.install("1.2.3.4", b"PK")
    assert [c[-3] for c in fake.calls if "appinstall" in c or "vd_appinstall" in c] == ["vd_appinstall", "appinstall"]


def test_install_failure_explains_signature_problem(monkeypatch):
    monkeypatch.setattr(td, "run", FakeSdb("install failed[118, -12], reason: Check certificate error"))
    with pytest.raises(RuntimeError, match="sertifika"):
        td.install("1.2.3.4", b"PK")


def test_connect_failure_mentions_developer_mode(monkeypatch):
    monkeypatch.setattr(td, "run", lambda args, timeout=60: "failed to connect to 1.2.3.4:26101")
    with pytest.raises(RuntimeError, match="Geliştirici Modu"):
        td.connect("1.2.3.4")
