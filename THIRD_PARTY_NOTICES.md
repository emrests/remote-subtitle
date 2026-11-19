# Üçüncü taraf bileşenler

Remote Subtitle (TR) GPL-3.0 ile lisanslıdır (bkz. `LICENSE`). Kurulum dosyası aşağıdaki bileşenleri içerir; her biri
kendi lisansıyla dağıtılır ve tümü GPL-3.0 ile uyumludur. Kaynak kodları ve lisans metinleri ilgili projelerde
bulunur; Python paketlerinin lisans dosyaları kurulum klasöründe `_internal\<paket>-<sürüm>.dist-info` altındadır.

## Kurulum dosyasına gömülü

| Bileşen | Sürüm | Lisans | Ne için |
|---|---|---|---|
| [pyremoteplay](https://github.com/ktnrg45/pyremoteplay) | 0.7.6 | GPL-3.0 | PS5'e doğrudan bağlantı |
| [pyps4-2ndscreen](https://github.com/ktnrg45/pyps4-2ndscreen) | 1.3.1 | LGPL-2.0-or-later | PS5 bulma (pyremoteplay bağımlılığı) |
| [PyAV](https://github.com/PyAV-Org/PyAV) | 19.0.2 | BSD-3-Clause | PS5 görüntüsünü çözme |
| [FFmpeg](https://ffmpeg.org) (PyAV ile gelen DLL'ler: avcodec, avformat, avutil…) | PyAV 19.0.2 içinde | LGPL-2.1-or-later | Görüntü çözme |
| [pywebview](https://github.com/r0x0r/pywebview) | 6.2.1 | BSD-3-Clause | Panel penceresi |
| [pythonnet](https://github.com/pythonnet/pythonnet), clr_loader | 3.2.1 / 0.3.1 | MIT | pywebview'in Windows katmanı |
| [bottle](https://bottlepy.org), proxy_tools | 0.13.4 / 0.1.0 | MIT | pywebview bağımlılıkları |
| [websockets](https://github.com/python-websockets/websockets) | 17.4 | BSD-3-Clause | Panel ve TV ile iletişim |
| [mss](https://github.com/BoboTiG/python-mss) | 10.2.0 | MIT | Ekran yakalama |
| [Pillow](https://python-pillow.org) | 12.2.0 | MIT-CMU | Görüntü işleme |
| [NumPy](https://numpy.org) | 2.5.0 | BSD-3-Clause (ve paketin belirttiği diğerleri) | Görüntü işleme |
| [PyWinRT](https://github.com/pywinrt/pywinrt) (winrt-runtime, winrt-Windows.*) | 4.1.0 | MIT | Windows OCR |
| [pyspellchecker](https://github.com/barrust/pyspellchecker) | 0.9.1 | MIT | OCR hatalarını düzeltme |
| [cryptography](https://github.com/pyca/cryptography) | 50.0.2 | Apache-2.0 OR BSD-3-Clause | TV sertifikası |
| [PyCryptodomex](https://www.pycryptodome.org) | 3.24.2 | BSD-2-Clause / Public Domain | PS5 oturumu |
| [requests](https://github.com/psf/requests), urllib3, idna, charset-normalizer | 2.34.2 / 2.8.0 / 3.20 / 3.5.2 | Apache-2.0 / MIT / BSD-3-Clause / MIT | Ağ istekleri |
| [certifi](https://github.com/certifi/python-certifi) | 2026.10.23 | MPL-2.0 | Kök sertifikalar |
| [aiohttp](https://github.com/aio-libs/aiohttp), async-timeout | 3.14.5 / 5.0.1 | Apache-2.0 AND MIT / Apache-2.0 | PS5 bağlantısı |
| [protobuf](https://github.com/protocolbuffers/protobuf) | 7.36.2 | BSD-3-Clause | PS5 bağlantısı |
| [lxml](https://lxml.de) | 6.1.3 | BSD-3-Clause | TV sertifika profili |
| [PyYAML](https://pyyaml.org) | 6.0.3 | MIT | Ayar dosyaları (bağımlılık) |
| netifaces-plus, pyee | 0.12.5 / 8.2.2 | MIT | Ağ / olaylar (bağımlılık) |
| cffi, pycparser, typing_extensions | 2.1.1 / 3.12 / 4.16.0 | MIT-0 / BSD-3-Clause / PSF-2.0 | Bağımlılıklar |
| [Python](https://www.python.org) çalışma zamanı | 3.14 | PSF-2.0 | Uygulama |
| [PyInstaller](https://pyinstaller.org) başlatıcısı | 6.22.3 | GPL-2.0-or-later, paketlenen programlar için istisnalı | Paketleme |
| sdb ([Tizen Studio](https://developer.tizen.org) aracı) | – | Apache-2.0 | Samsung TV'ye uygulama kurma |

## Samsung sertifikaları (`rsub/tv_ca`)

`vd_tizen_dev_author_ca.cer` (Samsung VD Author CA) ve `vd_tizen_dev_public2.crt` (VD DEVELOPER Public CA Class),
Samsung Electronics'in Tizen TV geliştirici sertifika zincirine ait **genel** CA sertifikalarıdır; gizli anahtar
içermezler. Samsung'un Tizen Studio sertifika eklentisiyle dağıtılır ve uygulama bunları, kullanıcının Samsung
hesabıyla kendi aldığı geliştirici sertifikasının zincirini kurmak için kullanır. Telif hakları Samsung
Electronics'e aittir.

## Kurulum sırasında indirilen (gömülü değil)

- [Ollama](https://ollama.com) (MIT): yoksa kurulum sihirbazı resmî siteden indirir.
- Çeviri modelleri (ör. TranslateGemma, [Gemma kullanım koşulları](https://ai.google.dev/gemma/terms)): Ollama üzerinden indirilir.
