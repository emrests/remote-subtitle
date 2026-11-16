# remote-subtitle

PS5 oyunlarındaki İngilizce altyazıları yerelde Türkçeye çevirip TV'de gösterir. Görüntü PC'ye Remote Play (chiaki-ng) penceresinden gelir.

## Geliştirme

```
pip install -r requirements.txt
python -m rsub              # panel penceresi + sistem tepsisi
python -m rsub --headless   # sadece sunucu (panel: http://127.0.0.1:8765/)
python -m pytest -q
```

Gösterim (TV / ikinci ekran): `http://<PC_IP>:8765/display.html`. Arkaya video için `?bg=video.mp4`.

Gerekenler: Ollama (`127.0.0.1:11434`; kurulum sihirbazı kurar). Windows OCR için ayrıca dil paketi gerekmez:
Latin alfabeli herhangi bir OCR dili (Türkçe Windows'ta `tr` hazır) İngilizce altyazıyı da okur.
İngilizce paketi kurmak (`Language.OCR~~~en-US~0.0.1.0`) şirket WSUS ortamlarında takılır; RDR2 ölçümünde gerek kalmadı.

Ayarlar ve profiller: `%APPDATA%\remote-subtitle\`.

## Ölçülen gecikme (2026-11-16, ikinci ekranda RDR2 oynanış videosu, 2560×1600)

- Yakalama: 4–14 ms, OCR (Windows, İngilizce paket olmadan): ortalama 4 ms / kare. 9 satırdan 8'i doğru okundu ("big fella" → "big fener").
- Çeviri (TranslateGemma 12B, RTX 5080 Laptop, tamamı VRAM'de): satır başına 225–471 ms. Ollama'nın kendi süresi ~250 ms;
  `localhost` yerine `127.0.0.1` kullanmak şart (Windows önce ::1'i dener, istek başına ~2 sn kaybettiriyordu).
