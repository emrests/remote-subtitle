import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from rsub import tizen_cert as tc


def test_dpapi_roundtrip():
    blob = tc.protect(b"gizli")
    assert blob != b"gizli" and tc.unprotect(blob) == b"gizli"


def test_author_csr_matches_certificate_manager_format():
    # Certificate Manager'ın gönderdiği: yalnız CN, RSA 2048, SHA-512
    csr = x509.load_pem_x509_csr(tc.author_csr(tc.new_key(), "TestUser"))
    assert csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "TestUser"
    assert csr.signature_hash_algorithm.name == "sha512" and csr.public_key().key_size == 2048


def test_distributor_csr_lists_tv_ids():
    csr = x509.load_pem_x509_csr(tc.distributor_csr(tc.new_key(), "a@b.com", ["TESTDUID12345", "ABCDEFGHIJKLM"]))
    san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert san.get_values_for_type(x509.UniformResourceIdentifier) == [
        "URN:tizen:packageid=", "URN:tizen:deviceid=TESTDUID12345", "URN:tizen:deviceid=ABCDEFGHIJKLM"]
    assert csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "TizenSDK"
    assert csr.subject.get_attributes_for_oid(NameOID.EMAIL_ADDRESS)[0].value == "a@b.com"


@pytest.mark.parametrize("body", [
    "access_token=T1&userId=U1&inputEmailID=a%40b.com",
    "code=" + "%7B%22access_token%22%3A%22T1%22%2C%22userId%22%3A%22U1%22%2C%22inputEmailID%22%3A%22a%40b.com%22%7D",
    "code=access_token%3DT1%26userId%3DU1%26inputEmailID%3Da%2540b.com",
])
def test_login_callback_formats(body):
    a = tc.parse_callback(body)
    assert (a.token, a.user_id) == ("T1", "U1") and a.email in ("a@b.com", "a%40b.com")


def test_login_callback_without_token_is_none():
    assert tc.parse_callback("code=") is None and tc.parse_callback("") is None


def test_multipart_body_like_certificate_manager():
    body, ctype = tc.multipart([("access_token", "T"), ("platform", "VD")], b"CSR", "author.csr")
    assert ctype == 'multipart/form-data; boundary="*****"'
    assert body.startswith(b"--*****\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Disposition: form-data; name=access_token\r\n\r\nT\r\n")
    assert b"name=csr; filename=author.csr\r\n\r\nCSR\r\n--*****--\r\n" in body


def test_read_pwd_strips_length_prefix_and_nul(monkeypatch):
    blob = tc.protect(b"parola\x00")
    assert tc.read_pwd(len(blob).to_bytes(4, "little") + blob) == "parola"
    assert tc.read_pwd(blob) == "parola"


def _issued(cn, duids=()):
    key = tc.new_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    b = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
         .serial_number(7).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=365)))
    if duids:
        b = b.add_extension(x509.SubjectAlternativeName(
            [x509.UniformResourceIdentifier(f"URN:tizen:deviceid={d}") for d in duids]), critical=False)
    return key, b.sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)


def test_save_load_keeps_keys_encrypted_and_reports_tvs(tmp_path, monkeypatch):
    monkeypatch.setenv("RSUB_HOME", str(tmp_path))
    ak, ac = _issued("TestUser")
    dk, dc = _issued("TizenSDK", ["TESTDUID12345"])
    c = tc.save(ak, ac, dk, dc, b"<Profile/>")
    assert c.info()["name"] == "TestUser" and c.duids == ["TESTDUID12345"]
    assert b"PRIVATE KEY" not in (tmp_path / "tv-cert" / "author.key.dpapi").read_bytes()
    assert len(tc.load().author.certs) == 2  # kendi + Samsung ara CA


def test_add_tvs_keeps_author_and_merges_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("RSUB_HOME", str(tmp_path))
    ak, ac = _issued("TestUser")
    dk, dc = _issued("TizenSDK", ["TESTDUID12345"])
    tc.save(ak, ac, dk, dc, b"<Profile/>")
    asked = {}

    def fake_dist(access, csr):
        ids = x509.load_pem_x509_csr(csr).extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        asked["duids"] = [u for u in ids.get_values_for_type(x509.UniformResourceIdentifier) if "deviceid" in u]
        return _issued("TizenSDK", ["ABCDEFGHIJKLM", "TESTDUID12345"])[1], b"<Profile/>"

    monkeypatch.setattr(tc, "request_author", lambda *a: pytest.fail("yazar yenilenmemeli"))
    monkeypatch.setattr(tc, "request_distributor", fake_dist)
    c = tc.add_tvs(tc.Access("T", "U", "a@b.com"), ["ABCDEFGHIJKLM"])
    assert asked["duids"] == ["URN:tizen:deviceid=ABCDEFGHIJKLM", "URN:tizen:deviceid=TESTDUID12345"]
    assert c.author.certs[0].public_bytes(serialization.Encoding.PEM) == ac


def test_bad_tv_id_rejected():
    with pytest.raises(ValueError):
        tc.create(tc.Access("T", "U"), "x", ["kısa"])
