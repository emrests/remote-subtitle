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

Gerekenler: Ollama (`localhost:11434`) ve Windows İngilizce OCR paketi
(`Add-WindowsCapability -Online -Name 'Language.OCR~~~en-US~0.0.1.0'`, yönetici). Kurulum sihirbazı bunları kendisi kurar.

Ayarlar ve profiller: `%APPDATA%\remote-subtitle\`.
