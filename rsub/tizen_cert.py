"""Samsung TV geliştirici sertifikası: Samsung hesabıyla giriş, yazar/dağıtıcı sertifikası alma, saklama.

Akış Tizen Studio'nun Samsung Certificate Extension'ından (org.tizen.common.cert) çıkarıldı:
- Giriş: tarayıcıda account.samsung.com açılır, Samsung sonucu http://localhost:4794/signin/callback'e gönderir
  (erişim anahtarı, kullanıcı kimliği, e-posta).
- Yazar: CSR → POST https://svdca.samsungqbe.com/apis/v3/authors (access_token, user_id, platform=VD, csr)
- Dağıtıcı: TV kimliklerini (DUID) içeren CSR → /apis/v3/distributors (+ privilege_level=Public,
  developer_type=Individual); aynı istek /apis/v1/distributors'a gidince TV'ye konacak device-profile.xml gelir.
Belgelenmemiş bir arayüzdür: Samsung değiştirirse Tizen Studio'nun Certificate Manager'ı yedek yoldur
(oluşturduğu profil "Tizen Studio sertifikasını içe aktar" ile alınır).

Özel anahtarlar Windows DPAPI ile (yalnız bu Windows kullanıcısı açabilir) %APPDATA%\\remote-subtitle\\tv-cert'te.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import re
import threading
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from . import store
from .tizen_sign import Signer

LOGIN_PORT = 4794
LOGIN_URL = ("https://account.samsung.com/mobile/account/check.do?serviceID=v285zxnl3h&actionID=StartOAuth2"
             f"&accessToken=Y&redirect_uri=http://localhost:{LOGIN_PORT}/signin/callback")
AUTHOR_URL = "https://svdca.samsungqbe.com/apis/v3/authors"
DISTRIBUTOR_URL = "https://svdca.samsungqbe.com/apis/v3/distributors"
PROFILE_URL = "https://svdca.samsungqbe.com/apis/v1/distributors"
CA_DIR = Path(__file__).parent / "tv_ca"
AUTHOR_CA = "vd_tizen_dev_author_ca.cer"
DISTRIBUTOR_CA = "vd_tizen_dev_public2.crt"
DUID = re.compile(r"^[A-Z0-9]{13}$")  # örn. CPCGVGAG2CWJK


# --- DPAPI (Windows kullanıcısına bağlı şifreleme; Certificate Manager da .pwd dosyalarında bunu kullanır) ---

class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    src, out = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), _Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI başarısız (başka bir Windows kullanıcısının dosyası olabilir)")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def protect(data: bytes) -> bytes:
    return _dpapi(data, True)


def unprotect(data: bytes) -> bytes:
    return _dpapi(data, False)


# --- CSR (Certificate Manager'ın ürettiğiyle aynı biçim: RSA 2048, SHA-512) ---

def new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def author_csr(key, name: str) -> bytes:
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    return x509.CertificateSigningRequestBuilder().subject_name(subject).sign(key, hashes.SHA512()).public_bytes(
        serialization.Encoding.PEM)


def distributor_csr(key, email: str, duids: list[str]) -> bytes:
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, "TizenSDK")]
    if email:
        attrs.insert(0, x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    san = [x509.UniformResourceIdentifier("URN:tizen:packageid=")]
    san += [x509.UniformResourceIdentifier(f"URN:tizen:deviceid={d}") for d in duids]
    return (x509.CertificateSigningRequestBuilder().subject_name(x509.Name(attrs))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .sign(key, hashes.SHA512()).public_bytes(serialization.Encoding.PEM))


# --- Samsung girişi ---

@dataclass
class Access:
    token: str
    user_id: str
    email: str = ""


def parse_callback(body: str) -> Access | None:
    """Samsung'un callback gövdesi: form alanları; değerler bazen "code" içinde JSON ya da a=b&c=d olarak gelir."""
    fields: dict[str, str] = {}

    def take(text: str):
        text = text.strip()
        if text.startswith("{"):
            try:
                fields.update({k: str(v) for k, v in json.loads(text).items()})
                return
            except ValueError:
                pass
        for k, vs in urllib.parse.parse_qs(text, keep_blank_values=True).items():
            fields[k] = vs[0]

    take(body)
    if "code" in fields and "access_token" not in fields:
        take(fields["code"])
    token = fields.get("access_token")
    user = fields.get("userId") or fields.get("user_id")
    if not token or not user:
        return None
    return Access(token, user, fields.get("inputEmailID") or fields.get("email", ""))


def login(timeout: float = 300, open_browser=webbrowser.open) -> Access:
    """Tarayıcıda Samsung girişi; sonuç localhost:4794'e gelene kadar bekler."""
    result: dict = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def _handle(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
            query = urllib.parse.urlsplit(self.path).query
            access = parse_callback(body) or parse_callback(query)
            ok = access is not None
            if ok:
                result["access"] = access
            else:  # biçim beklenmedikse ne geldiğini (değerler olmadan) kaydet: hata ayıklamak için
                keys = sorted(set(urllib.parse.parse_qs(body)) | set(urllib.parse.parse_qs(query)))
                result["error"] = f"Samsung girişinden beklenmeyen yanıt (alanlar: {', '.join(keys) or 'yok'})"
            msg = ("Giriş tamam. remote-subtitle'a dönebilirsiniz." if ok else result["error"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            done.set()

        do_GET = do_POST = _handle

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", LOGIN_PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        open_browser(LOGIN_URL)
        if not done.wait(timeout):
            raise TimeoutError("Samsung girişi zaman aşımına uğradı")
    finally:
        srv.shutdown()
        srv.server_close()
    if "access" not in result:
        raise RuntimeError(result.get("error", "Samsung girişi başarısız"))
    return result["access"]


# --- Samsung sertifika sunucusu ---

def multipart(fields: list[tuple[str, str]], csr: bytes, csr_name: str) -> tuple[bytes, str]:
    """Certificate Manager'ın gönderdiği gövdenin aynısı (sınır "*****")."""
    out = b""
    for name, value in fields:
        out += (f"--*****\r\nContent-Type: text/plain; charset=utf-8\r\n"
                f"Content-Disposition: form-data; name={name}\r\n\r\n{value}\r\n").encode()
    out += (f"--*****\r\nContent-Disposition: form-data; name=csr; filename={csr_name}\r\n\r\n").encode()
    out += csr + b"\r\n--*****--\r\n"
    return out, 'multipart/form-data; boundary="*****"'


def _post(url: str, fields, csr: bytes, csr_name: str) -> bytes:
    body, ctype = multipart(fields, csr, csr_name)
    req = urllib.request.Request(url, body, {"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            err = json.loads(detail).get("error", {})
            detail = err.get("description") or err.get("name") or detail
        except (ValueError, AttributeError):
            pass
        if e.code == 429:
            detail = "çok fazla istek; biraz bekleyip tekrar deneyin"
        raise RuntimeError(f"Samsung sertifika sunucusu {e.code}: {detail}") from None


def request_author(access: Access, csr: bytes) -> bytes:
    return _post(AUTHOR_URL, [("access_token", access.token), ("user_id", access.user_id), ("platform", "VD")],
                 csr, "author.csr")


def request_distributor(access: Access, csr: bytes) -> tuple[bytes, bytes]:
    fields = [("access_token", access.token), ("user_id", access.user_id), ("privilege_level", "Public"),
              ("developer_type", "Individual"), ("platform", "VD")]
    crt = _post(DISTRIBUTOR_URL, fields, csr, "distributor.csr")
    profile = _post(PROFILE_URL, fields, csr, "distributor.csr")
    return crt, profile


# --- saklama ---

def cert_dir() -> Path:
    return store.home() / "tv-cert"


def _ca(name: str):
    return x509.load_pem_x509_certificate((CA_DIR / name).read_bytes())


def _load_pem_cert(data: bytes):
    m = re.search(rb"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", data, re.S)
    return x509.load_pem_x509_certificate(m.group(0)) if m else x509.load_der_x509_certificate(data)


@dataclass
class TvCert:
    author: Signer
    distributor: Signer
    device_profile: bytes
    duids: list[str] = field(default_factory=list)
    name: str = ""
    expires: str = ""

    def info(self) -> dict:
        return {"name": self.name, "duids": self.duids, "expires": self.expires}


def duids_of(cert) -> list[str]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return []
    return [u.split("=", 1)[1] for u in san.get_values_for_type(x509.UniformResourceIdentifier)
            if u.startswith("URN:tizen:deviceid=")]


def _make(author: Signer, dist: Signer, profile: bytes) -> TvCert:
    a = author.certs[0]
    name = a.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    expires = min(author.certs[0].not_valid_after_utc, dist.certs[0].not_valid_after_utc).date().isoformat()
    return TvCert(author, dist, profile, duids_of(dist.certs[0]), name[0].value if name else "", expires)


def save(author_key, author_crt: bytes, dist_key, dist_crt: bytes, profile: bytes) -> TvCert:
    d = cert_dir()
    d.mkdir(parents=True, exist_ok=True)
    pem = lambda k: k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
    (d / "author.key.dpapi").write_bytes(protect(pem(author_key)))
    (d / "author.crt").write_bytes(author_crt)
    (d / "distributor.key.dpapi").write_bytes(protect(pem(dist_key)))
    (d / "distributor.crt").write_bytes(dist_crt)
    (d / "device-profile.xml").write_bytes(profile)
    return load()


def load() -> TvCert | None:
    d = cert_dir()
    if not (d / "distributor.crt").exists():
        return None
    key = lambda n: serialization.load_pem_private_key(unprotect((d / n).read_bytes()), None)
    author = Signer(key("author.key.dpapi"), [_load_pem_cert((d / "author.crt").read_bytes()), _ca(AUTHOR_CA)])
    dist = Signer(key("distributor.key.dpapi"),
                  [_load_pem_cert((d / "distributor.crt").read_bytes()), _ca(DISTRIBUTOR_CA)])
    return _make(author, dist, (d / "device-profile.xml").read_bytes())


def create(access: Access, name: str, duids: list[str], author_key=None, author_crt: bytes | None = None) -> TvCert:
    """Yeni sertifika (yazar yoksa onu da alır). Yeni TV eklenince yalnız dağıtıcı yenilenir, yazar aynı kalır
    — aynı yazarla imzalı uygulama güncellenebilir."""
    bad = [d for d in duids if not DUID.match(d)]
    if bad or not duids:
        raise ValueError(f"Geçersiz TV kimliği: {', '.join(bad) or 'yok'}")
    if author_key is None:
        author_key = new_key()
        author_crt = request_author(access, author_csr(author_key, name or "remote-subtitle"))
    dist_key = new_key()
    dist_crt, profile = request_distributor(access, distributor_csr(dist_key, access.email, duids))
    return save(author_key, author_crt, dist_key, dist_crt, profile)


def add_tvs(access: Access, duids: list[str]) -> TvCert:
    cur = load()
    if cur is None:
        return create(access, "", duids)
    all_duids = sorted(set(cur.duids) | set(duids))
    a_crt = cur.author.certs[0].public_bytes(serialization.Encoding.PEM)
    return create(access, cur.name, all_duids, cur.author.key, a_crt)


def read_pwd(data: bytes) -> str:
    """Certificate Manager .pwd: 4 bayt uzunluk (little-endian) + DPAPI bloğu; içerik UTF-16 ya da UTF-8."""
    if len(data) > 4 and int.from_bytes(data[:4], "little") == len(data) - 4:
        data = data[4:]
    raw = unprotect(data).rstrip(b"\x00")  # C dizgisi gibi sonda NUL ile saklanıyor
    return raw.decode("utf-8")


def import_tizen_studio(folder: Path) -> TvCert:
    """Tizen Studio Certificate Manager'ın oluşturduğu profil (author.p12 + .pwd, distributor.p12 + .pwd,
    device-profile.xml). Şifreler DPAPI'li .pwd dosyalarından okunur; kullanıcıdan şifre istenmez."""
    folder = Path(folder)

    def signer(n: str) -> Signer:
        return Signer.from_p12((folder / f"{n}.p12").read_bytes(), read_pwd((folder / f"{n}.pwd").read_bytes()))

    author, dist = signer("author"), signer("distributor")
    if len(author.certs) < 2:
        author.certs.append(_ca(AUTHOR_CA))
    if len(dist.certs) < 2:
        dist.certs.append(_ca(DISTRIBUTOR_CA))
    a_crt = author.certs[0].public_bytes(serialization.Encoding.PEM)
    d_crt = dist.certs[0].public_bytes(serialization.Encoding.PEM)
    return save(author.key, a_crt, dist.key, d_crt, (folder / "device-profile.xml").read_bytes())
