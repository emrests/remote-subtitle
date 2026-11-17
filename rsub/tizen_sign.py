"""Tizen web uygulaması (.wgt) imzalama — Tizen Studio gerekmez.

Biçim, Tizen Studio'nun imzalayıcısından (org.tizen.common.sign) çıkarıldı: W3C "XML Digital Signatures for
Widgets". İki imza: author-signature.xml (yazar) ve signature1.xml (dağıtıcı; yazar imzasını da kapsar).
Dosya özetleri SHA-256, SignedInfo exclusive C14N + RSA-SHA256, #prop nesnesi C14N 1.1 ile özetlenir.
"""
from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.asymmetric import padding
from lxml import etree

DSIG = "http://www.w3.org/2000/09/xmldsig#"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"
SIGNATURE_FILES = ("author-signature.xml",)


def _is_signature(name: str) -> bool:
    base = name.rsplit("/", 1)[-1]
    return base in SIGNATURE_FILES or (base.startswith("signature") and base.endswith(".xml") and base[9:-4].isdigit())


@dataclass
class Signer:
    key: object                 # RSA özel anahtar
    certs: list                 # [kendi sertifikası, ara CA, ...]

    @classmethod
    def from_p12(cls, blob: bytes, password: str) -> "Signer":
        if "\x00" in password:  # kütüphane NUL'lu şifrede çöküyor ve hata mesajına şifreyi yazıyor
            raise ValueError("Sertifika şifresi okunamadı")
        try:
            key, cert, extra = pkcs12.load_key_and_certificates(blob, password.encode())
        except Exception:  # noqa: BLE001 — mesaj şifre içerebilir: yerine güvenli mesaj
            raise ValueError("Sertifika dosyası açılamadı (şifre yanlış ya da dosya bozuk)") from None
        return cls(key, [cert, *extra])


def _digest(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def _reference(uri: str, digest: str, transform: str | None = None) -> str:
    t = (f'<Transforms>\n<Transform Algorithm="{transform}"></Transform>\n</Transforms>\n') if transform else ""
    return (f'<Reference URI="{uri}">\n{t}<DigestMethod Algorithm="{SHA256}"></DigestMethod>\n'
            f'<DigestValue>{digest}</DigestValue>\n</Reference>\n')


def _wrap64(data: bytes) -> str:
    s = base64.b64encode(data).decode()
    return "\n".join(s[i:i + 76] for i in range(0, len(s), 76))


def _signature_xml(files: list[tuple[str, bytes]], signer: Signer, role: str, sig_id: str) -> bytes:
    """files: (paketteki yol, içerik) — imzalanacak sırayla."""
    obj = (f'<Object Id="prop"><SignatureProperties xmlns:dsp="http://www.w3.org/2009/xmldsig-properties">'
           f'<SignatureProperty Id="profile" Target="#{sig_id}"><dsp:Profile URI="http://www.w3.org/ns/widgets-digsig#profile"></dsp:Profile></SignatureProperty>'
           f'<SignatureProperty Id="role" Target="#{sig_id}"><dsp:Role URI="http://www.w3.org/ns/widgets-digsig#role-{role}"></dsp:Role></SignatureProperty>'
           f'<SignatureProperty Id="identifier" Target="#{sig_id}"><dsp:Identifier></dsp:Identifier></SignatureProperty>'
           f'</SignatureProperties></Object>')
    refs = "".join(_reference(quote(name, safe="/"), _digest(data)) for name, data in files)
    # #prop özeti, nesnenin belge içindeki C14N 1.1 hali: obj zaten kanonik; tek fark Signature'dan miras ad alanı.
    # (lxml alt öğe c14n'i torunlara sahte xmlns="" ekliyor ve TV imzayı reddediyordu.)
    prop_c14n = obj.replace('<Object Id="prop">', f'<Object xmlns="{DSIG}" Id="prop">', 1).encode()
    refs += _reference("#prop", _digest(prop_c14n), "http://www.w3.org/2006/12/xml-c14n11")
    signed_info = (f'<SignedInfo>\n<CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"></CanonicalizationMethod>\n'
                   f'<SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"></SignatureMethod>\n'
                   f'{refs}</SignedInfo>')
    si = etree.fromstring(f'<Signature xmlns="{DSIG}">{signed_info}</Signature>'.encode()).find(f"{{{DSIG}}}SignedInfo")
    value = signer.key.sign(etree.tostring(si, method="c14n", exclusive=True), padding.PKCS1v15(), hashes.SHA256())
    certs = "".join(f"<X509Certificate>\n{_wrap64(c.public_bytes(serialization.Encoding.DER))}\n</X509Certificate>\n"
                    for c in signer.certs)
    return (f'<Signature xmlns="{DSIG}" Id="{sig_id}">\n{signed_info}\n'
            f'<SignatureValue>\n{_wrap64(value)}\n</SignatureValue>\n'
            f'<KeyInfo>\n<X509Data>\n{certs}</X509Data>\n</KeyInfo>\n{obj}\n</Signature>').encode()


def sign_wgt(src: Path, author: Signer, distributor: Signer) -> bytes:
    """src klasöründeki uygulamayı imzalayıp .wgt (zip) içeriğini döndürür. Eski imza dosyaları atlanır."""
    src = Path(src)
    files = sorted((p.relative_to(src).as_posix(), p.read_bytes()) for p in src.rglob("*")
                   if p.is_file() and not _is_signature(p.relative_to(src).as_posix()))
    author_xml = _signature_xml(files, author, "author", "AuthorSignature")
    dist_xml = _signature_xml([("author-signature.xml", author_xml), *files], distributor, "distributor",
                              "DistributorSignature")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data)
        z.writestr("author-signature.xml", author_xml)
        z.writestr("signature1.xml", dist_xml)
    return out.getvalue()
