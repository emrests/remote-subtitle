# Remote Subtitle (TR)

Oyunlardaki İngilizce altyazıları bilgisayarda okuyup yerel bir çeviri modeliyle Türkçeye çevirir ve çeviriyi
**Samsung TV'de oyun görüntüsünün üstünde** (ya da bilgisayarda kaynak pencerenin üstünde) gösterir.
İnternete metin gönderilmez: metin tanıma Windows OCR, çeviri bilgisayardaki Ollama ile yapılır.

```
PS5 ──HDMI──▶ Samsung TV  (Remote Subtitle TV uygulaması: HDMI görüntüsü + üstünde çeviri katmanı)
 │                ▲
 │ Remote Play    │ çeviri kutuları (Wi-Fi, 8765 numaralı bağlantı noktası)
 ▼                │
Bilgisayar: görüntü → altyazı bölgesi → OCR → çeviri (Ollama) → kutu çizimi
```

## Gerekenler

- Windows 10/11 (64 bit).
- Ekran kartı: çeviri modeli VRAM'e göre seçilir (TranslateGemma 4B ≈ 5 GB, 12B ≈ 10 GB, 27B ≈ 20 GB VRAM).
- Kaynak olarak biri:
  - **PS5** (doğrudan bağlantı, Remote Play): PS5 ile bilgisayar aynı ağda; Remote Play için bir PSN hesabı.
  - Bilgisayardaki herhangi bir **pencere** (chiaki-ng, video oynatıcı, tarayıcı…).
- TV'de göstermek için: **Samsung Tizen TV** (denendi: QE75QN800DTXTK, 2024) bilgisayarla aynı ağda ve bir
  **Samsung hesabı**. Tizen Studio gerekmez.

## Kurulum

### 1. Masaüstü uygulaması

1. [Releases](../../releases) sayfasından `remote-subtitle-setup.exe` dosyasını indirip çalıştırın (yönetici izni ister).
2. Sihirbaz şunları yapar:
   - Uygulamayı `Program Files\remote-subtitle` klasörüne kurar.
   - Bilgisayarda **Ollama** yoksa indirip kurar (yaklaşık 1,9 GB). `OllamaSetup.exe` dosyası setup'ın yanında
     duruyorsa ya da daha önce indirildiyse yeniden indirilmez.
   - TV'nin bağlanabilmesi için güvenlik duvarına **TCP 8765** izni ekler (özel ve ortak ağ).
   - İsteğe bağlı: Windows ile başlat, masaüstü kısayolu.
3. Uygulama ilk açılışta ekran kartınıza uygun çeviri modelini kendiliğinden indirir
   (**Çeviri modeli** sekmesinden değiştirilebilir). Üst şeritteki *Ollama*, *Model* ve *OCR* göstergeleri yeşil olmalı.

Windows OCR için ayrıca dil paketi gerekmez: Latin alfabeli herhangi bir OCR dili (Türkçe Windows'ta hazır)
İngilizce altyazıyı da okur.

### 2. Kaynak: PS5 (doğrudan bağlantı)

**Kurulum** sekmesi → *PS5 — doğrudan bağlantı*:

1. **PSN hesabı**: *Sony giriş sayfasını aç* → Remote Play için kullanacağınız hesapla giriş yapın. Giriş sonrası
   açılan sayfa hata gibi görünebilir; adres çubuğundaki adresin tamamını kopyalayıp kutuya yapıştırın → *Kaydet*.
   Oyunu oynadığınız hesaptan ayrı ikinci bir PSN hesabı kullanabilirsiniz.
2. **Eşleştirme** (bir kez): PS5'te o hesapla oturum açın → *Ayarlar › Sistem › Uzaktan Oynama › Cihazı Eşleştir*.
   PS5'in IP adresini (*Ayarlar › Ağ › Bağlantı Durumu*) ve PS5 ekranındaki 8 haneli kodu girip *Eşleştir*.
3. *PS5'i kaynak yap*.

PS5 aynı anda tek Remote Play bağlantısı kabul eder: chiaki-ng ya da PS Remote Play uygulaması açıksa kapatın.
TV'de "Uzaktan Oynama bağlandı" bildirimi çıkmasın diye PS5'te *Uzaktan Oynama Bağlantı Durumunu Gizle*'yi açın.

Yedek yol: chiaki-ng penceresini (ya da başka bir pencereyi) kaynak olarak seçin. Pencere küçültülmemeli ve
başka bir pencerenin altında kalmamalı.

### 3. Altyazı bölgesi

**Kaynak ve bölge** sekmesi: kaynağı seçin → *Görüntü al* → görüntü üzerinde altyazının çıktığı alanı fareyle
çizin. Ayarlar oyun profiline kaydedilir (üstteki profil listesi: *Yeni / Kopyala / Sil*). *Oyun dili* sekmesinde oyunun
dünyasını (örneğin "1899 Vahşi Batı"), konuşma tarzını, argo/küfür sözlüğünü ve sabit terimleri; *Karakterler*
sekmesinde konuşmacı renklerini tanımlayabilirsiniz.

*Çeviriyi göster*: **Bu bilgisayarda** (pencere kaynağında, orijinal altyazının üstünde) ve/veya **TV'de**.

### 4. Samsung TV uygulaması

**Kurulum** sekmesi → *Samsung TV uygulaması*:

1. **TV'de Geliştirici Modu**: TV'de *Uygulamalar* ekranını açın, kumandada sırayla **1 2 3 4 5** tuşlayın.
   *Developer mode*: **On**, *Host PC IP*: sekmede yazan bilgisayar adresi. Sonra TV'yi kapatıp açın
   (güç tuşuna basılı tutun).
2. **TV'leri ara**: geliştirici modundaki TV bulunur; model ve TV kimliği (DUID) okunur. Bulunamazsa TV'nin IP
   adresini elle girip *Ekle*.
3. **Samsung sertifikası**: *Samsung ile giriş yap ve sertifika oluştur* → tarayıcıda kendi Samsung hesabınızla
   giriş yapın. Samsung, geliştirici uygulamalarının yalnızca sertifikada kimliği geçen TV'lere kurulmasına izin
   verir; yeni TV eklediğinizde aynı düğmeyle sertifika yenilenir. Sertifikalar
   `%APPDATA%\remote-subtitle\tv-cert` içinde Windows DPAPI ile şifreli saklanır.
   Tizen Studio Certificate Manager ile oluşturulmuş bir sertifikanız varsa *Tizen Studio sertifikasını içe
   aktar* ile de kullanabilirsiniz (`%USERPROFILE%\SamsungCertificate\<profil>`).
4. **Kur**: listede TV'nin yanındaki *Kur*. Uygulama imzalanır (bilgisayarın adresi içine yazılır), TV'ye kurulur
   ve açılır. TV'de *Uygulamalar* listesinde **Remote Subtitle (TR)** olarak görünür.
5. TV uygulaması ilk açılışta HDMI 1'i (o girişte cihaz yoksa bağlı ilk HDMI girişini) gösterir. PS5 başka
   girişteyse kumandadaki **Kırmızı tuş** ile HDMI numarasını (ve gerekirse bilgisayar adresini) girin, **OK**.

Bilgisayarın IP adresi değişirse *Kur* ile yeniden kurun (ya da TV'de Kırmızı tuş ile adresi düzeltin).

## Kullanım

1. Bilgisayarda Remote Subtitle açık olsun ve **Çeviriyi başlat** basılı olsun.
2. TV'de **Remote Subtitle (TR)** uygulamasını açın. PS5 görüntüsü tam ekran gelir, çeviriler üstünde çıkar.
3. **Oyunu bu uygulamanın içinden izleyin.** Kumandadan TV'nin kendi HDMI kaynağına geçerseniz uygulama arka plana
   düşer ve çeviri görünmez. **Geri** tuşu uygulamadan çıkar.

*Kaynak ve bölge › Çeviriyi göster › TV'de* satırı TV ile iletişimi gösterir (TV'deki sayfa 2 saniyede bir bildirir):

| Durum | Anlamı |
|---|---|
| 🟢 TV ile iletişim var · ekranda · N çeviri kutusu alındı | Her şey yolunda |
| 🟠 TV uygulaması arka planda: çeviri görünmez | TV'de kaynak değişmiş ya da başka uygulama açılmış |
| 🟠 TV bağlı, yanıt bekleniyor | Bağlantı yeni açıldı |
| 🔴 TV yanıt vermiyor (N sn) | TV uygulaması donmuş ya da kapanmış |
| 🔴 TV uygulaması açık değil | Bağlantı yok |

## Sorun giderme

| Belirti | Çözüm |
|---|---|
| TV'de "192.168.x.x geçici olarak çökmüş" / `ERR_CONNECTION_REFUSED` | Bilgisayarda Remote Subtitle açık değil. Açın, TV uygulamasını kapatıp yeniden açın. |
| TV bağlanamıyor | TV ve bilgisayar aynı ağda olmalı; güvenlik duvarında TCP 8765 izni (sihirbaz ekler) olmalı. |
| Çeviri TV'de görünmüyor | Oyunu Remote Subtitle uygulamasının içinden izleyin (HDMI kaynağına geçmeyin); panelde TV durumunu kontrol edin. Profilde *TV'de* işaretli olmalı. |
| TV uygulaması *Uygulamalar* listesinde ya da aramada yok | *Kur* ile yeniden kurun; liste görünmezse TV'yi kapatıp açın. |
| Kurulumda "imza/sertifika reddedildi" | TV'nin kimliği sertifikada yok: *Samsung ile giriş yap ve sertifika oluştur* ile yenileyin, sonra *Kur*. |
| TV bulunamıyor | Geliştirici Modu açık mı, *Host PC IP* bu bilgisayar mı? Ayardan sonra TV yeniden başlatılmalı. |
| "Another Remote Play session is connected" / PS5 oturumu açılamadı | chiaki-ng, PS Remote Play ya da uygulamanın ikinci bir kopyası PS5'e bağlı. Kapatıp *Durumu yenile*. |
| Şirket bilgisayarında Tizen Studio Certificate Manager silindi | Antivirüs dosyayı engelliyor; uygulamanın kendi *Samsung ile giriş yap* yolunu kullanın ya da BT'den istisna isteyin. |

Ayarlar, profiller ve TV sertifikası: `%APPDATA%\remote-subtitle\`.

## Geliştirme

```
pip install -r requirements.txt
pip install --no-deps pyremoteplay==0.7.6   # netifaces bağımlılığı Python 3.14'te derlenmiyor; yerine netifaces-plus
python -m rsub              # panel penceresi (kapatınca tamamen kapanır)
python -m rsub --headless   # sadece sunucu (panel: http://127.0.0.1:8765/)
python -m pytest -q
```

Gösterim sayfası (TV / ikinci ekran / tarayıcı): `http://<PC_IP>:8765/display.html`. Arkaya video için `?bg=video.mp4`.
TV uygulamasının ayrıntıları: [tizen/README.md](tizen/README.md).

### Kurulum dosyasını derleme

Gerekenler: PyInstaller, Inno Setup 6 (`winget install JRSoftware.InnoSetup`) ve TV kurulumu için `sdb.exe`
(Tizen Studio'dan; `C:\tizen-studio\tools\sdb.exe` varsa betik pakete kopyalar).

```
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build.ps1
```

Çıktı: `packaging\Output\remote-subtitle-setup.exe`. Betik PowerShell 5.1 içinden çıktısı yönlendirilerek
çalıştırılırsa PyInstaller'ın bilgi satırlarını hata sayar; ayrı bir `powershell -File` ile çalıştırın.

Sürüm yayınlama (GitHub CLI):

```
gh release create v<sürüm> packaging\Output\remote-subtitle-setup.exe --title "Remote Subtitle (TR) <sürüm>" --notes-file notlar.md
```

Sürüm numarası: `packaging/installer.iss` (`AppVersion`) ve `tizen/config.xml` (`version`).

## Ölçülen gecikme (2026-11-16, ikinci ekranda RDR2 oynanış videosu, 2560×1600)

- Yakalama: 4–14 ms, OCR (Windows, İngilizce paket olmadan): ortalama 4 ms / kare. 9 satırdan 8'i doğru okundu ("big fella" → "big fener").
- Çeviri (TranslateGemma 12B, RTX 5080 Laptop, tamamı VRAM'de): satır başına 225–471 ms. Ollama'nın kendi süresi ~250 ms;
  `localhost` yerine `127.0.0.1` kullanmak şart (Windows önce ::1'i dener, istek başına ~2 sn kaybettiriyordu).

## Lisans

GPL-3.0 (bkz. [LICENSE](LICENSE)). Kurulum dosyasına gömülü üçüncü taraf bileşenler ve lisansları: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
