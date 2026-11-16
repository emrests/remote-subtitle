# remote-subtitle Masaüstü Uygulaması: Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `server.py` adlı komut satırı iskeletini bir masaüstü uygulamasına dönüştürmek. Uygulamada şunlar olacak:
- pywebview penceresinde açılan kontrol paneli
- oyun profilleri
- konuşmacı ayırma
- model seçimi ve indirme
- sistem tepsisi
- kurulum sihirbazı

**Architecture:** Arka uç, `rsub/` paketindeki Python kodu. Tek bir port (8765) üzerinde çalışan `websockets` sunucusu üç işi birlikte yapar:
- `web/` klasöründeki statik dosyaları GET ile sunar.
- Gösterim ekranlarına yayın yapar.
- Panelden gelen komutları işler. Komutlar yalnızca localhost'tan kabul edilir.

Yakalama → OCR → sabitleme → konuşmacı ayırma → çeviri döngüsü aynı asyncio döngüsünde çalışır. Panel ve gösterim sayfası, satırları ekrana çizen aynı `subtitle.js` dosyasını kullanır. Böylece paneldeki önizleme TV'dekiyle birebir aynı olur.

**Tech Stack:** Python 3.14, mss, websockets 17, winrt (Windows OCR), pywebview 6, pystray + Pillow, pytest, PyInstaller, Inno Setup 6. Arayüz framework'süz HTML/CSS/JS ile yazılır.

**Spec:** `docs/superpowers/specs/2026-11-16-kontrol-paneli-design.md`

## Global Constraints
- Yalnızca Windows 11. Uygulama, ilk iş olarak `SetProcessDpiAwareness(2)` çağrısıyla monitör bazında DPI farkında hale gelir.
- Kullanıcı verileri `%APPDATA%\remote-subtitle\` altında tutulur: `settings.json` ve `profiles\<ad>.json`. Testler `RSUB_HOME` ortam değişkeniyle bu yolu değiştirir.
- Port 8765. Panel, gösterim sayfası ve WebSocket bu tek porttan çalışır.
- Ayar değiştiren her komut yalnızca `127.0.0.1` veya `::1` adresinden kabul edilir. Diğer adreslerden gelen komutlar `{"type":"reply","ok":false,"error":"forbidden"}` yanıtını alır.
- Ollama adresi `http://localhost:11434`.
- Hedef gecikme: satır ekranda belirdikten sonra çeviri 1 saniyenin altında görünmeli. Son 10 satırın ortalaması 1000 ms'yi aşarsa panelde "Daha küçük bir model deneyin" uyarısı çıkar.
- Arayüz metinleri Türkçe.
- Bir ayar değiştiğinde uygulamayı yeniden başlatmak gerekmemeli.

## Review Focus
1. **Hedef pencere kayboluyor.** chiaki kapanıyor ya da küçültülüyor. Döngü çökmemeli, durum satırında "Pencere bulunamadı" görünmeli, döngü 1 saniye bekleyip yeniden denemeli. Test: Task 5 `test_run_survives_missing_window`.
2. **Ollama kapalı ya da model yok.** Çeviri hatası satırı düşürmemeli. İngilizce metin `tr` alanına konup gösterilmeli ve durum satırına hata yazılmalı. Test: Task 5 `test_translate_failure_falls_back_to_english`.
3. **Yanlış konuşmacı.** `WARNING:`, `Note:` ya da cümle ortasındaki saat (`at 10:30`) konuşmacı sayılmamalı. Test: Task 2 `test_not_speakers`.
4. **Bozuk profil dosyası** ya da eksik anahtarlı eski bir profil. Uygulama açılmalı ve eksik alanlar varsayılanlarla doldurulmalı. Test: Task 1 `test_load_profile_fills_defaults` ve `test_corrupt_profile_falls_back`.
5. **Profil adında dosya adı için yasak karakter var** (`Spider-Man: 2`, `a/b`). Profil yine kaydedilebilmeli. Test: Task 1 `test_profile_name_with_illegal_chars`.

---

## Dosya yapısı

| Dosya | Sorumluluk |
|---|---|
| `rsub/store.py` | Ayarları ve profilleri JSON olarak okuma/yazma, varsayılanlar |
| `rsub/speaker.py` | OCR metnini `[(konuşmacı, replik)]` listesine bölme |
| `rsub/translate.py` | İstem metni, terim listesi, Ollama çağrısı, önbellek |
| `rsub/models.py` | Model kataloğu, VRAM okuma, model önerisi, kurulu modeller, indirme |
| `rsub/capture.py` | DPI ayarı, pencere ve monitör listesi, hedef dikdörtgen, oranlı bölgeyi piksele çevirme, ekran yakalama, PNG anlık görüntü |
| `rsub/ocr.py` | Windows OCR (`server.py` dosyasından taşınır) |
| `rsub/pipeline.py` | Satır sabitleme, satırları oluşturma, ana döngü, durum bilgisi |
| `rsub/web.py` | Tek port: statik dosyalar, WebSocket protokolü, komutlar |
| `rsub/app.py` | Giriş noktası: sunucu thread'i, pywebview penceresi, tepsi, tek kopya kontrolü |
| `web/subtitle.js` | `renderSubtitle(el, lines, style)` (panel ve gösterim sayfası ortak kullanır) |
| `web/display.html` | TV / ikinci ekran gösterim sayfası |
| `web/panel.html`, `panel.css`, `panel.js` | Kontrol paneli |
| `packaging/rsub.spec`, `packaging/installer.iss` | PyInstaller ve Inno Setup dosyaları |
| `tests/test_*.py` | pytest testleri |

`server.py` ve `display/` Task 7'de silinir. Mevcut `stable()`, `ocr()`, `make_ocr()`, `translate()` ve `PROMPT` yeni modüllere taşınır.

## Protokol (tüm görevler için ortak)
Sunucudan istemciye giden mesajlar:
- `{"type":"style","style":Style}`
- `{"type":"lines","lines":[Line]}`. `Line = {"speaker":str|null, "color":str|null, "en":str, "tr":str}`. Boş liste altyazıyı kaldırır.
- `{"type":"status","status":Status}`. `Status = {"ollama":bool, "model":str, "modelReady":bool, "ocrEnglish":bool, "window":bool, "clients":int, "last":{"capture":ms,"ocr":ms,"translate":ms}|null, "avgMs":int|null, "slow":bool, "error":str|null, "pull":{"model":str,"pct":int}|null}`
- `{"type":"reply","id":int,"ok":bool,"data":any,"error":str|null}`

İstemciden sunucuya giden komutlar `{"id":int,"cmd":str,...}` biçimindedir. Hepsi yalnızca localhost'tan kabul edilir:
- `get_state` → `{settings, profile, profiles:[str], models:[ModelInfo], vramMb, ip, port}`
- `select_profile{name}`, `save_profile{profile}`, `copy_profile{name,newName}`, `delete_profile{name}`
- `list_sources` → `[{"id":"monitor:1","label":...}, {"id":"<pencere başlığı>","label":...}]`
- `snapshot{source}` → `{"png":base64,"width":int,"height":int}`
- `save_settings{settings}`, `pull_model{model}`, `launch_chiaki`

Veri biçimleri:
- `Style = {"font":"Segoe UI","size":48,"color":"#ffffff","bg":"#000000","bgOpacity":0.75,"position":"bottom","offset":60,"nameColor":"#ffd166"}`
- `Profile = {"name":str,"source":str,"region":[x,y,w,h] (0–1 arası oranlar),"style":Style,"glossary":{en:tr},"speakers":{ad:{"color":str|null,"voice":null}}}`
  - `source` değeri bir pencere başlığının bir parçası (büyük/küçük harf duyarsız) ya da `"monitor:N"` olur. Bu, spec'teki "pencere adı boşsa mutlak koordinat" kuralının yerini alır. Monitör de bir kaynak olduğu için tek bir oranlı bölge biçimi yeterli oluyor.
- `Settings = {"profile":"Varsayılan","model":"translategemma:12b","chiakiPath":""}`

---

### Task 1: Ayar ve profil deposu

**Files:**
- Create: `rsub/__init__.py` (boş), `rsub/store.py`, `tests/test_store.py`, `tests/conftest.py`
- Modify: `requirements.txt` (pywebview, pystray, Pillow, pytest ekle), `.gitignore` (`.pytest_cache/`, `build/`, `dist/`)

**Interfaces:**
- Produces: `home() -> Path`, `DEFAULT_STYLE: dict`, `default_profile(name: str) -> dict`, `load_settings() -> dict`, `save_settings(s: dict) -> None`, `list_profiles() -> list[str]`, `load_profile(name: str) -> dict`, `save_profile(p: dict) -> None`, `delete_profile(name: str) -> None`, `copy_profile(name: str, new: str) -> dict`

- [ ] **Step 1: Write failing tests**. `conftest.py` içinde `autouse` bir fixture `RSUB_HOME`'u `tmp_path`'e ayarlar.

```python
def test_defaults_when_empty():
    assert store.load_settings() == {"profile": "Varsayılan", "model": "translategemma:12b", "chiakiPath": ""}
    assert store.load_profile("Varsayılan")["region"] == [0.0, 0.7, 1.0, 0.3]

def test_save_and_list_roundtrip():
    p = store.default_profile("RDR2"); p["glossary"] = {"Arthur": "Arthur"}
    store.save_profile(p)
    assert store.list_profiles() == ["RDR2"] and store.load_profile("RDR2")["glossary"] == {"Arthur": "Arthur"}

def test_load_profile_fills_defaults():
    (store.home() / "profiles").mkdir(parents=True)
    (store.home() / "profiles" / "Eski.json").write_text('{"name":"Eski","style":{"size":30}}', encoding="utf-8")
    p = store.load_profile("Eski")
    assert p["style"]["size"] == 30 and p["style"]["nameColor"] == "#ffd166" and p["speakers"] == {}

def test_corrupt_profile_falls_back():
    (store.home() / "profiles").mkdir(parents=True)
    (store.home() / "profiles" / "Bozuk.json").write_text("{not json", encoding="utf-8")
    assert store.load_profile("Bozuk")["name"] == "Bozuk"

def test_profile_name_with_illegal_chars():
    store.save_profile(store.default_profile("Spider-Man: 2/b"))
    assert store.list_profiles() == ["Spider-Man: 2/b"]

def test_copy_and_delete():
    store.save_profile(store.default_profile("A"))
    store.copy_profile("A", "B"); store.delete_profile("A")
    assert store.list_profiles() == ["B"]
```

- [ ] **Step 2: Run** `python -m pytest tests/test_store.py -q`. Beklenen: FAIL (modül yok).
- [ ] **Step 3: Implement `rsub/store.py`.**
  - `home()` yolu `RSUB_HOME` değişkeninden, yoksa `%APPDATA%\remote-subtitle` klasöründen alır.
  - Dosya adı, profil adının URL-safe base64 kodlaması olur. Gerçek ad dosyanın içindeki `name` alanından okunur.
  - Yükleme sırasında eksik anahtarlar ve `style` alanları varsayılanlarla birleştirilir.
  - JSON okunamazsa `default_profile(name)` döner.
  - Dosyalar UTF-8 ile ve `ensure_ascii=False` ayarıyla yazılır.
- [ ] **Step 4: Run** aynı komut. Beklenen: 6 passed.
- [ ] **Step 5: Commit** `feat: ayar ve profil deposu`

### Task 2: Konuşmacı ayırma

**Files:** Create `rsub/speaker.py`, `tests/test_speaker.py`

**Interfaces:**
- Produces: `split_speakers(text: str) -> list[tuple[str | None, str]]`

- [ ] **Step 1: Write failing tests**

```python
def test_single():          assert split_speakers("Arthur: Hello my friend!") == [("Arthur", "Hello my friend!")]
def test_no_speaker():      assert split_speakers("We need to move.") == [(None, "We need to move.")]
def test_multi_word():      assert split_speakers("Dutch van der Linde: Arthur!") == [(None, "Dutch van der Linde: Arthur!")]  # 4 kelime: isim değil
def test_three_words():     assert split_speakers("Uncle Bob Jr: Hey") == [("Uncle Bob Jr", "Hey")]
def test_two_speakers():    assert split_speakers("Arthur: Ready? Sadie: Always.") == [("Arthur", "Ready?"), ("Sadie", "Always.")]
def test_not_speakers():
    assert split_speakers("WARNING: Low health") == [(None, "WARNING: Low health")]
    assert split_speakers("Meet me at 10:30 tonight") == [(None, "Meet me at 10:30 tonight")]
def test_empty():           assert split_speakers("") == []
```

`Note: ...` gibi büyük harfle başlayan tek kelimelik ön ekler kalıba uyar ve konuşmacı sayılır. Bu bilinen bir sınırdır. Panelde karakter listesinden silinebilir ama yine de konuşmacı olarak görünür. Bunun için test yazılmaz.

- [ ] **Step 2: Run** `python -m pytest tests/test_speaker.py -q`. Beklenen: FAIL.
- [ ] **Step 3: Implement.** İsim kalıbı: `(?:^|(?<=[.!?…"] ))([A-Z][\w'.-]*(?: [A-Z][\w'.-]*){0,2}):\s+`. İsim, metnin başında ya da bir cümle sonu işaretinin ardından gelmelidir. Bulunan isim tamamen büyük harfliyse ve 1 karakterden uzunsa (`isupper()`) atlanır. Metin, bulunan isim konumlarından bölünür. İlk isimden önce kalan metin `(None, ...)` olarak eklenir.
- [ ] **Step 4: Run** aynı komut. Beklenen: 7 passed.
- [ ] **Step 5: Commit** `feat: konuşmacı ayırma`

### Task 3: Çeviri ve model kataloğu

**Files:** Create `rsub/translate.py`, `rsub/models.py`, `tests/test_translate.py`, `tests/test_models.py`

**Interfaces:**
- Produces (`translate.py`): `build_prompt(text: str, glossary: dict[str, str]) -> str`, `translate(text: str, model: str, glossary: dict, cache: dict) -> str`. Hata durumunda exception fırlatır; yakalamak çağıranın işi.
- Produces (`models.py`): `CATALOG: list[dict]`, `recommend(vram_mb: int | None) -> str`, `gpu_vram_mb() -> int | None`, `installed() -> set[str]`, `ollama_up() -> bool`, `pull(model: str, on_pct: Callable[[int], None]) -> None`, `model_infos(vram_mb) -> list[dict]`

`CATALOG` sıralaması iyiden kötüye. `min_vram_mb` ve `size_gb` değerleri tahmindir. Uygulayıcı `ollama show` ya da ollama.com üzerinden doğrular, etiket adları farklıysa düzeltir:

```python
CATALOG = [
  {"id": "translategemma:27b", "label": "TranslateGemma 27B", "size_gb": 17, "min_vram_mb": 20000, "note": "En iyi kalite, en yavaş"},
  {"id": "translategemma:12b", "label": "TranslateGemma 12B", "size_gb": 8,  "min_vram_mb": 10000, "note": "Önerilen denge"},
  {"id": "gemma3:12b",         "label": "Gemma 3 12B",        "size_gb": 8,  "min_vram_mb": 10000, "note": "Genel model, terim listesine daha iyi uyar"},
  {"id": "translategemma:4b",  "label": "TranslateGemma 4B",  "size_gb": 3.3,"min_vram_mb": 5000,  "note": "Hızlı, düşük VRAM"},
]
```

- [ ] **Step 1: Write failing tests**

```python
def test_prompt_contains_text_and_only_relevant_terms():
    p = build_prompt("Arthur rides to Valentine.", {"Arthur": "Arthur", "Valentine": "Valentine", "Dutch": "Dutch"})
    assert p.endswith("Arthur rides to Valentine.") and "Valentine = Valentine" in p and "Dutch" not in p
def test_prompt_without_glossary_is_base_prompt():
    assert "=" not in build_prompt("Hi.", {})
def test_translate_uses_cache(monkeypatch):
    calls = []; monkeypatch.setattr(translate_mod, "_generate", lambda model, prompt: calls.append(1) or "Selam.")
    cache = {}; translate("Hi.", "m", {}, cache); translate("Hi.", "m", {}, cache)
    assert len(calls) == 1
def test_recommend():
    assert recommend(16303) == "translategemma:12b"
    assert recommend(24576) == "translategemma:27b"
    assert recommend(6144) == "translategemma:4b"
    assert recommend(None) == "translategemma:4b"
def test_model_infos_marks_fit():
    infos = model_infos(16303)
    assert [i["fits"] for i in infos] == [False, True, True, True] and sum(i["recommended"] for i in infos) == 1
```

- [ ] **Step 2: Run** `python -m pytest tests/test_translate.py tests/test_models.py -q`. Beklenen: FAIL.
- [ ] **Step 3: Implement.**
  - `PROMPT` metni `server.py` dosyasından aynen taşınır.
  - `build_prompt`: metinde geçen terimler (büyük/küçük harf duyarsız) varsa çevrilecek metnin önüne şu satır eklenir: `"Use these fixed translations: A = B; C = D."`
  - `_generate(model, prompt)`: Ollama'nın `/api/generate` uç noktasını çağırır. Parametreler: `stream=False`, `keep_alive="30m"`, `temperature=0`, `timeout=30`.
  - `gpu_vram_mb`: `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits` çalıştırır. Hata alırsa `None` döner.
  - `installed`: `/api/tags` uç noktasını çağırır.
  - `ollama_up`: `/api/version` uç noktasını 1 saniye zaman aşımıyla çağırır.
  - `pull`: `/api/pull` uç noktasını `stream=True` ile çağırır. Gelen her satırda `completed/total` oranından yüzde hesaplanır ve `on_pct` çağrılır.
- [ ] **Step 4: Run** aynı komut. Beklenen: PASS.
- [ ] **Step 5: Commit** `feat: çeviri istemi, terim listesi ve model kataloğu`

### Task 4: Yakalama ve OCR

**Files:** Create `rsub/capture.py`, `rsub/ocr.py`, `tests/test_capture.py`

**Interfaces:**
- Produces (`capture.py`):
  - `set_dpi_aware() -> None`
  - `list_sources() -> list[dict]`: görünür ve başlığı boş olmayan pencereler ile `monitor:N` kaynakları
  - `target_rect(source: str) -> tuple[int, int, int, int] | None`: `(left, top, width, height)`, sanal masaüstü pikselinde
  - `to_pixels(region: list[float], rect: tuple) -> dict`: mss'nin beklediği `{left, top, width, height}` sözlüğü
  - `grab(sct, box: dict)`
  - `snapshot_png(source: str) -> tuple[bytes, int, int] | None`
- Produces (`ocr.py`): `make_ocr()`, `has_english() -> bool`, `async ocr(engine, shot) -> str`. Mevcut kod taşınır; uyarı `print` yerine `has_english()` ile sorgulanır.

- [ ] **Step 1: Write failing tests**

```python
def test_to_pixels_scales_with_window():
    assert to_pixels([0.0, 0.7, 1.0, 0.3], (100, 50, 1000, 500)) == {"left": 100, "top": 400, "width": 1000, "height": 150}
def test_to_pixels_negative_monitor():
    assert to_pixels([0.5, 0.5, 0.5, 0.5], (-2560, 471, 2560, 1600))["left"] == -1280
def test_to_pixels_min_size():
    assert to_pixels([0.5, 0.5, 0.0, 0.0], (0, 0, 100, 100))["width"] >= 1
def test_monitor_source_resolves():
    assert target_rect("monitor:1") is not None
def test_unknown_window_is_none():
    assert target_rect("no-such-window-xyz") is None
```

- [ ] **Step 2: Run** `python -m pytest tests/test_capture.py -q`. Beklenen: FAIL.
- [ ] **Step 3: Implement.** Win32 çağrıları için `ctypes` kullanılır:
  - `EnumWindows` + `IsWindowVisible` + `GetWindowTextW` ile pencereler listelenir. Kaynak adı başlığın içinde (büyük/küçük harf duyarsız) geçen ilk görünür pencere seçilir.
  - Pencere `IsIconic` ise (küçültülmüşse) `None` döner.
  - Dikdörtgen `GetClientRect` + `ClientToScreen` ile alınır, yani çerçeve ve başlık çubuğu hariç iç alan.
  - `monitor:N` kaynağı `mss.MSS().monitors[N]` ile çözülür.
  - `set_dpi_aware` için `ctypes.windll.shcore.SetProcessDpiAwareness(2)` çağrılır; hata alınırsa yok sayılır.
  - PNG üretmek için `mss.tools.to_png` kullanılır.
- [ ] **Step 4: Run** aynı komut. Beklenen: 5 passed.
- [ ] **Step 5: Commit** `feat: pencere takipli yakalama ve OCR modülü`

### Task 5: Pipeline

**Files:** Create `rsub/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes:
  - Task 1: `store.save_profile`
  - Task 2: `split_speakers`
  - Task 3: `translate`
  - Task 4: `target_rect`, `to_pixels`, `grab`, `ocr`
- Produces:
  - `stable(state: dict, text: str) -> str | None`: `server.py` dosyasından aynen taşınır, mevcut selftest'i pytest testine çevrilir.
  - `build_lines(text: str, profile: dict, tr: Callable[[str], str]) -> tuple[list[dict], bool]`: Dönen `bool`, profile yeni konuşmacı eklendiyse `True` olur.
  - `class Runtime` alanları: `settings`, `profile`, `status: dict`, `emit: Callable[[dict], None]`, `cache: dict`, `engine`
  - `async run(rt: Runtime, interval: float = 0.15) -> None`
  - `Runtime.timings: deque(maxlen=10)`

- [ ] **Step 1: Write failing tests**

```python
P = {"glossary": {}, "speakers": {"Arthur": {"color": "#ff0000", "voice": None}}, "style": {"nameColor": "#ffd166"}}
def test_build_lines_colors_and_new_speaker():
    lines, changed = build_lines("Arthur: Hi. Sadie: Bye.", copy.deepcopy(P), lambda s: s.upper())
    assert lines == [{"speaker": "Arthur", "color": "#ff0000", "en": "Hi.", "tr": "HI."},
                     {"speaker": "Sadie", "color": "#ffd166", "en": "Bye.", "tr": "BYE."}]
    assert changed is True
def test_build_lines_empty_clears():  assert build_lines("", copy.deepcopy(P), str) == ([], False)
def test_translate_failure_falls_back_to_english():
    def boom(s): raise OSError("ollama down")
    lines, _ = build_lines("We ride.", copy.deepcopy(P), boom)
    assert lines[0]["tr"] == "We ride."
def test_stable_sequence():
    s = {"prev": None, "sent": ""}
    assert [stable(s, t) for t in ["", "Hel", "Hello", "Hello", "Hello", "", ""]] == [None, None, None, "Hello", None, None, ""]
async def test_run_survives_missing_window(monkeypatch):  # pytest-asyncio yerine asyncio.run kullanılır
    ...  # target_rect -> None; run() 1.2 s içinde çökmez, rt.status["window"] False olur, emit hiç çağrılmaz
```

- [ ] **Step 2: Run** `python -m pytest tests/test_pipeline.py -q`. Beklenen: FAIL.
- [ ] **Step 3: Implement.**
  - `build_lines`: Çeviri hatasında `tr = en` olur ve hata, ileride `status["error"]` alanına yazılmak üzere döndürülür ya da kaydedilir. Uygulayıcı bunu `Runtime` içinde tutar.
  - `run` döngüsü her turda `rt.profile`'ı yeniden okur. Böylece panelde yapılan değişiklik bir sonraki karede geçerli olur, yeniden başlatma gerekmez.
  - Pencere yoksa `status.window = False` yapılır ve 1 saniye beklenir.
  - Satır gönderildiğinde `emit({"type":"lines",...})` çağrılır. Süreler `timings`'e eklenir, `status.avgMs` ve `status.slow` (ortalama > 1000 ms) güncellenir.
  - `changed` ise `store.save_profile` çağrılır.
  - Çeviri `asyncio.to_thread` ile çalışır.
- [ ] **Step 4: Run** aynı komut. Beklenen: PASS.
- [ ] **Step 5: Commit** `feat: pipeline, konuşmacılı satırlar`

### Task 6: Web sunucusu ve protokol

**Files:** Create `rsub/web.py`, `tests/test_web.py`

**Interfaces:**
- Consumes: Task 1, 3, 4 ve 5'in tüm `Produces` maddeleri.
- Produces:
  - `async serve_app(port: int = 8765, web_dir: Path = ...) -> None`: sunucuyu ve `pipeline.run` döngüsünü birlikte çalıştırır.
  - `local_ip() -> str`: UDP soket hilesiyle (`connect("8.8.8.8", 80)`, veri gönderilmez) bulunur.

- [ ] **Step 1: Write failing tests.** Testler sunucuyu rastgele bir portta başlatır. Pipeline, monkeypatch ile hiçbir şey yapmayan bir döngüyle değiştirilir.

```python
async def test_static_and_state():
    # GET /display.html -> 200, gövdede "subtitle.js" geçer
    # ws: {"id":1,"cmd":"get_state"} -> reply ok, data.settings.model == "translategemma:12b", data.port == port
async def test_new_client_gets_style_first():
    # bağlanınca gelen ilk mesaj type == "style"
async def test_save_profile_broadcasts_style():
    # ikinci istemci açıkken save_profile ile style.size=60 gönderilir -> ikinci istemci {"type":"style","style":{"size":60,...}} alır
async def test_forbidden_from_non_local(monkeypatch):
    # is_local() False olacak şekilde patch'lenir -> save_settings reply {"ok": False, "error": "forbidden"}
async def test_unknown_path_404():
    # GET /../rsub/store.py -> 404 (path traversal yok)
```

- [ ] **Step 2: Run** `python -m pytest tests/test_web.py -q`. Beklenen: FAIL.
- [ ] **Step 3: Implement.**
  - `websockets.asyncio.server.serve` çağrısına `process_request` verilir. Upgrade başlığı olmayan GET isteklerinde dosya `web_dir` altından sunulur; yol `resolve()` ile çözülür ve `web_dir` dışına çıkıyorsa 404 döner. `/` adresi `panel.html`'e yönlendirilir. Content-Type `mimetypes` ile belirlenir.
  - Bağlanan istemciye önce `style`, sonra `status`, en son da son `lines` mesajı gönderilir.
  - Komutlar bir sözlük üzerinden ilgili işleve yönlendirilir. Engelleyen çağrılar (`snapshot`, `pull_model`) `asyncio.to_thread` ile çalıştırılır.
  - `pull_model` indirme ilerlemesini `status.pull` alanına yazar ve 0,5 saniyede bir `status` yayını yapar.
  - `status` mesajı ayrıca her saniye yayınlanır.
  - `launch_chiaki`, `subprocess.Popen([settings["chiakiPath"]])` çağırır.
- [ ] **Step 4: Run** aynı komut. Beklenen: PASS.
- [ ] **Step 5: Commit** `feat: tek portlu web sunucusu ve komut protokolü`

### Task 7: Ortak altyazı çizimi ve gösterim sayfası

**Files:**
- Create: `web/subtitle.js`, `web/display.html`
- Delete: `display/index.html`, `server.py`
- Modify: `README.md` (çalıştırma komutu `python -m rsub.app`)

**Interfaces:**
- Produces (`subtitle.js`):
  - `renderSubtitle(container: HTMLElement, lines: Line[], style: Style): void`
  - `connectSubtitles(url: string, onMsg: (msg) => void): void`: yeniden bağlanmayı da yönetir, 2 saniye aralıkla.

- [ ] **Step 1:** `subtitle.js` yazılır.
  - Her `Line` ayrı bir blok olarak çizilir: `<div class="line"><span class="name" style="color">Arthur:</span> Merhaba dostum!</div>`.
  - `style` alanları CSS değişkenlerine yazılır: font, boyut, renk, `rgba(bg, opacity)`, top/bottom ve offset.
  - Metin `textContent` ile basılır, `innerHTML` kullanılmaz (OCR metniyle XSS riski olmasın).
- [ ] **Step 2:** `display.html` yazılır. Sabit 1920×1080 tuval, isteğe bağlı `?bg=` video arka planı (mevcut sayfadan taşınır), `?host=` parametresi yoksa `location.host` kullanılır.
- [ ] **Step 3: Verify.** `python -m rsub.app --headless` çalıştırılır. Bu bayrak Task 9'da eklenecek; o zamana kadar `python -c "import asyncio, rsub.web as w; asyncio.run(w.serve_app())"` kullanılır. Ardından `http://127.0.0.1:8765/display.html` Playwright ile açılır. Sayfanın yüklenmesi beklenir; `{"type":"lines","lines":[{"speaker":"Arthur","color":"#ff0000","en":"Hi","tr":"Selam"}]}` mesajı test için `emit` ile gönderilir. Beklenen: ekran görüntüsünde kırmızı "Arthur:" ve beyaz "Selam" görünür.
- [ ] **Step 4: Commit** `feat: ortak altyazı çizimi ve gösterim sayfası; eski iskelet kaldırıldı`

### Task 8: Kontrol paneli

**Files:** Create `web/panel.html`, `web/panel.css`, `web/panel.js`

**Interfaces:**
- Consumes: Task 6 protokolü, Task 7 `renderSubtitle`.

Uygulayıcı bu görevden önce `frontend-design:frontend-design` skill'ini yükler. Spec'teki başarısızlık ölçütü: panel geliştirici aracı gibi görünmemeli.

Görsel kurallar:
- koyu tema
- tek yazı ailesi (Segoe UI Variable)
- 8 px boşluk ızgarası
- tutarlı form kontrolleri
- dar pencerede de taşmayan düzen (en az 1100×720)

Yerleşim:

```
┌ Üst çubuk: profil seçici [Yeni][Kopyala][Sil] ··········· durum noktaları (Ollama·Model·OCR·Pencere·Ekranlar) ┐
├ Sol menü ──────┬ İçerik ──────────────────────────────────────────────────────────────────────────────────────┤
│ Kaynak & Bölge │ Kaynak listesi + anlık görüntü; üstünde sürüklenebilir/yeniden boyutlanır dikdörtgen          │
│ Görünüm        │ Form (font, boyut, renk, arka plan+saydamlık, konum, kenar boşluğu, isim rengi) | canlı önizleme│
│ Terimler       │ İki sütunlu düzenlenebilir tablo (İngilizce → Türkçe), satır ekle/sil                         │
│ Karakterler    │ Görülen konuşmacılar: ad, renk seçici, (ses: "Dublaj aşamasında"), sil                        │
│ Çeviri modeli  │ Katalog kartları iyiden kötüye; VRAM uyarısı, "Önerilen" rozeti, indir/seç, ilerleme çubuğu   │
│ Bağlantı       │ TV adresi http://<ip>:8765/display.html (kopyala), bağlı ekran sayısı, chiaki yolu + Başlat   │
└ Alt çubuk: son satır EN → TR ve süreler (yakala/ocr/çeviri ms); slow ise sarı uyarı ┘
```

- [ ] **Step 1:** HTML iskeleti ve CSS yazılır.
- [ ] **Step 2:** `panel.js` yazılır.
  - Açılışta `get_state` çağrılır.
  - Form değişikliklerinde profil 300 ms debounce ile `save_profile` komutuyla kaydedilir.
  - Önizleme `renderSubtitle` ile, örnek satır `Arthur: Merhaba dostum!` kullanılarak çizilir.
  - Bölge çizimi anlık görüntü üzerinde pointer olaylarıyla yapılır. Değer `[x/w, y/h, bw/w, bh/h]` oranlarına çevrilip kaydedilir; görüntünün gerçek boyutuna göre ölçeklenir.
  - Model indirme ilerlemesi `status.pull` alanından okunur.
- [ ] **Step 3: Verify.** Sunucu çalışırken `http://127.0.0.1:8765/` adresi Playwright ile 1280×800 boyutunda açılıp her sekmenin ekran görüntüsü alınır. Kontrol edilecekler:
  - (a) Boyut değiştirildiğinde önizleme ve ayrı bir sekmede açık `display.html` aynı anda güncellenir.
  - (b) `monitor:2` seçilip dikdörtgen çizildiğinde `%APPDATA%` (test için `RSUB_HOME`) altındaki profil dosyasında oranlı `region` alanı yazılır.
  - (c) Konsolda hata yoktur.
- [ ] **Step 4: Commit** `feat: kontrol paneli`

### Task 9: Masaüstü kabuğu: pencere, tepsi, tek kopya

**Files:** Create `rsub/app.py`, `rsub/__main__.py`, `web/icon.png` (Pillow ile üretilen basit bir simge; aynı simgeden `packaging/icon.ico` da üretilir)

**Interfaces:**
- Consumes: `web.serve_app`, `capture.set_dpi_aware`
- Produces: `main(argv: list[str] | None = None) -> None`. Bayraklar: `--headless` (pencere ve tepsi olmadan sadece sunucu), `--port`.

- [ ] **Step 1: Implement.**
  - Tek kopya kontrolü: `CreateMutexW("Global\\remote-subtitle")` çağrılır. `GetLastError() == 183` dönerse uygulama zaten çalışıyordur; çalışan kopyanın paneli açılır (`webbrowser` değil, mevcut pencereyi göstermek için 8765 portuna bir `show` komutu gönderilir) ve bu kopya çıkar. Bunun için Task 6'ya küçük bir ekleme yapılır: localhost'tan gelen `show` komutu, `on_show` callback'ini çağırır.
  - Sunucu, daemon thread içinde `asyncio.run(serve_app())` ile çalışır.
  - Pencere: `webview.create_window("remote-subtitle", "http://127.0.0.1:8765/", width=1280, height=800, min_size=(1100,720))`.
  - Pencerenin `closing` olayında pencere gizlenir ve `False` döndürülerek kapanma iptal edilir.
  - pystray simgesi ayrı bir thread'de çalışır. Menüsü: "Paneli aç" (`window.show()`) ve "Çıkış" (`window.destroy()` + `os._exit(0)`).
- [ ] **Step 2: Verify.** `python -m rsub` çalıştırılır. Beklenenler:
  - Pencere açılır.
  - Pencere kapatılınca tepside simge kalır ve `http://127.0.0.1:8765/display.html` hâlâ yanıt verir.
  - İkinci kez `python -m rsub` çalıştırılınca yeni pencere açılmaz, mevcut pencere öne gelir.
  - Tepside "Çıkış" seçilince port kapanır.
- [ ] **Step 3: Commit** `feat: masaüstü penceresi, sistem tepsisi, tek kopya`

### Task 10: Uçtan uca test: ikinci ekranda YouTube

Kod yazılmaz, doğrulama yapılır. Bu adımdan önce kullanıcının iki şey yapmış olması gerekir:
- İngilizce OCR paketini kurmak
- Ollama'yı kurmak

Bunlar sonra kurulum sihirbazının işi olacak; şimdilik elle kurulur.

- [ ] **Step 1:** İkinci monitörde İngilizce altyazılı bir oynanış videosu açılır. Panelde kaynak olarak videonun penceresi seçilir (başlıkta "YouTube" geçer) ve altyazı bölgesi çizilir. Model sekmesinden `translategemma:12b` indirilir.
- [ ] **Step 2:** Tarayıcıda `display.html` açılır. Beklenenler:
  - Türkçe satırlar görünür.
  - Alt çubukta süreler yazar.
  - Ortalama 1000 ms'nin altındadır. Değilse ölçülen rakamlar kullanıcıya raporlanır.
- [ ] **Step 3:** Video penceresi küçültülür. Beklenen: "Pencere bulunamadı" durumu görünür. Pencere geri açılınca çeviri devam eder.
- [ ] **Step 4:** Ölçüm sonuçları README'ye kısa bir "Ölçülen gecikme" notu olarak eklenir. Commit `docs: uçtan uca ölçüm`.

### Task 11: Paketleme ve kurulum sihirbazı

**Files:** Create `packaging/rsub.spec`, `packaging/installer.iss`, `packaging/build.ps1`

- [ ] **Step 1:** `rsub.spec` yazılır. `rsub/__main__.py` giriş noktası, `web/` klasörü `datas` olarak eklenir. `hiddenimports` içine `winrt.windows.*` modülleri ve `webview.platforms.edgechromium` yazılır. `console=False`, çıktı tek klasör (onedir) olur.
- [ ] **Step 2:** `build.ps1` yazılır:
  - `pyinstaller packaging/rsub.spec` çalıştırır.
  - `OllamaSetup.exe` dosyasını `https://ollama.com/download/OllamaSetup.exe` adresinden `packaging/vendor/` klasörüne indirir (klasör `.gitignore`'a eklenir).
  - Inno Setup derleyicisi `ISCC.exe` ile `installer.iss` dosyasını derler.
- [ ] **Step 3:** `installer.iss` yazılır:
  - `PrivilegesRequired=admin`.
  - `[Tasks]` altında `startup`: "Windows ile başlat", HKCU `Run` kayıt anahtarı.
  - `[Run]` adımları:
    1. Ollama kurulu değilse (`{localappdata}\Programs\Ollama\ollama.exe` yoksa) `OllamaSetup.exe /VERYSILENT /NORESTART` çalıştırılır. Bu sessiz kurulum bayraklarını uygulayıcı doğrular.
    2. `powershell -NoProfile -Command "Add-WindowsCapability -Online -Name 'Language.OCR~~~en-US~0.0.1.0'"` çalıştırılır.
    3. `netsh advfirewall firewall add rule name="remote-subtitle" dir=in action=allow protocol=TCP localport=8765 profile=private` çalıştırılır.
  - `[UninstallRun]` altında güvenlik duvarı kuralı silinir.
  - Son sayfada "chiaki-ng'yi indir" bağlantısı gösterilir: `https://github.com/chiaki-ng/chiaki-ng/releases`.
- [ ] **Step 4: Verify.** `powershell -File packaging/build.ps1` çalıştırılır. Beklenen: `packaging/Output/remote-subtitle-setup.exe` oluşur. Kurulum testi kullanıcının makinesinde yönetici izni ve onay gerektirir; uygulayıcı kurulumu çalıştırmaz, sadece derlemeyi doğrular.
- [ ] **Step 5: Commit** `build: PyInstaller + Inno Setup kurulum sihirbazı`
