import base64
import datetime
import hashlib
import io
import zipfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from lxml import etree

from rsub.tizen_sign import Signer, sign_wgt

DS = "{http://www.w3.org/2000/09/xmldsig#}"


def _signer(cn):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    ca = cert  # testte zincirin ikinci halkası olarak aynısı yeterli
    return Signer(key, [cert, ca])


def _app(tmp_path):
    (tmp_path / "config.xml").write_text("<widget/>")
    (tmp_path / "main.js").write_text("console.log(1)")
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "a b.png").write_bytes(b"\x89PNG")
    return tmp_path


def _verify(xml: bytes, files: dict, cert_key):
    """Bağımsız doğrulama: her Reference'ın özeti ve SignedInfo imzası (exclusive c14n, RSA-SHA256)."""
    root = etree.fromstring(xml)
    si = root.find(DS + "SignedInfo")
    uris = []
    for ref in si.findall(DS + "Reference"):
        uri = ref.get("URI")
        uris.append(uri)
        if uri == "#prop":
            obj = root.find(DS + "Object")
            data = etree.tostring(obj, method="c14n")
        else:
            from urllib.parse import unquote
            data = files[unquote(uri)]
        assert base64.b64decode(ref.find(DS + "DigestValue").text) == hashlib.sha256(data).digest(), uri
    sig = base64.b64decode(root.find(DS + "SignatureValue").text)
    cert_key.public_key().verify(sig, etree.tostring(si, method="c14n", exclusive=True), padding.PKCS1v15(), hashes.SHA256())
    return root, uris


def test_wgt_has_author_and_distributor_signatures_that_verify(tmp_path):
    author, dist = _signer("Emre"), _signer("TizenSDK")
    wgt = sign_wgt(_app(tmp_path), author, dist)
    z = zipfile.ZipFile(io.BytesIO(wgt))
    files = {n: z.read(n) for n in z.namelist()}
    assert {"config.xml", "main.js", "img/a b.png", "author-signature.xml", "signature1.xml"} <= set(files)

    a_root, a_uris = _verify(files["author-signature.xml"], files, author.key)
    assert a_root.get("Id") == "AuthorSignature"
    assert sorted(a_uris) == sorted(["config.xml", "main.js", "img/a%20b.png", "#prop"])
    role = a_root.find(".//{http://www.w3.org/2009/xmldsig-properties}Role").get("URI")
    assert role.endswith("#role-author")

    d_root, d_uris = _verify(files["signature1.xml"], files, dist.key)
    assert d_root.get("Id") == "DistributorSignature"
    assert "author-signature.xml" in d_uris and "signature1.xml" not in d_uris
    assert d_root.find(".//{http://www.w3.org/2009/xmldsig-properties}Role").get("URI").endswith("#role-distributor")


def test_key_info_carries_cert_chain(tmp_path):
    author, dist = _signer("Emre"), _signer("TizenSDK")
    z = zipfile.ZipFile(io.BytesIO(sign_wgt(_app(tmp_path), author, dist)))
    root = etree.fromstring(z.read("author-signature.xml"))
    certs = [x509.load_der_x509_certificate(base64.b64decode("".join(c.text.split())))
             for c in root.iter(DS + "X509Certificate")]
    assert len(certs) == 2 and certs[0] == author.certs[0]


def test_old_signatures_in_source_are_not_signed_again(tmp_path):
    app = _app(tmp_path)
    (app / "signature1.xml").write_text("eski")
    (app / "author-signature.xml").write_text("eski")
    z = zipfile.ZipFile(io.BytesIO(sign_wgt(app, _signer("a"), _signer("d"))))
    assert z.read("signature1.xml") != b"eski"
    root = etree.fromstring(z.read("author-signature.xml"))
    assert "signature1.xml" not in [r.get("URI") for r in root.iter(DS + "Reference")]


def test_signer_from_pkcs12(tmp_path):
    s = _signer("Emre")
    blob = pkcs12.serialize_key_and_certificates(
        b"a", s.key, s.certs[0], [s.certs[1]], serialization.BestAvailableEncryption(b"pw"))
    loaded = Signer.from_p12(blob, "pw")
    assert loaded.certs[0] == s.certs[0] and len(loaded.certs) == 2
