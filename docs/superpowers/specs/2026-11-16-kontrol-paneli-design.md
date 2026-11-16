# remote-subtitle: Masaüstü uygulaması, oyun profilleri ve kurulum sihirbazı

## Niyet
PS5 oyunlarındaki İngilizce altyazılar, ev ağındaki Windows laptopta yerelde okunur, Türkçeye çevrilir ve Samsung TV'de gösterilir. Görüntü PS5'ten Remote Play (chiaki-ng) penceresi üzerinden gelir. Laptop TV'den başka bir odada durur, bu yüzden capture kart ve kamera elendi.

Mevcut durum: `server.py` adlı bir komut satırı iskeleti var. Elle girilen sabit bir ekran bölgesini okuyor; Windows OCR, satır sabitleme, Ollama çevirisi, WebSocket ve süre logu çalışıyor. `display/index.html` basit bir gösterim sayfası.

Bu tur onu kullanıcıya hazır bir masaüstü uygulamasına çeviriyor:
- Kullanıcı arayüzden bölge seçer, görünüm ayarlar ve oyun profilleri tanımlar.
- Konuşmacı ayrılır ve ismi farklı renkte gösterilir.
- Uygulama kurulum sihirbazıyla tek seferde kurulur.

Kullanıcı arayüzün profesyonel görünmesini önemsiyor.

Uzun vadeli zincir: OCR → çeviri → **dublaj**, yani karaktere uygun sesle sesli okuma. Dublaj bu turda yapılmıyor, ama konuşmacı bilgisi şimdiden veri olarak taşınıyor. Dublaj geldiğinde her karakterin sesi profilde saklanacak.

## Hedefler
1. **Masaüstü penceresi:** pywebview ile Windows'un WebView2 motoru üzerinde açılır, tarayıcı sekmesi değildir. İçinde kontrol paneli var.
2. **Görüntü kaynağı:** Kaynak, adıyla takip edilen bir pencere (`chiaki`, `YouTube` vb.) ve o pencereye göre bir bölgedir. Pencere taşınsa da bölge onunla gider. Pencere adı boşsa bölge mutlak ekran koordinatı olur. Tüm monitörler desteklenir; ikinci monitörün koordinatları negatif olabilir.
3. **Bölge seçimi:** Panel, hedef pencerenin (ya da seçilen monitörün) anlık görüntüsünü gösterir. Kullanıcı üstüne fareyle dikdörtgen çizer, bölge pencereye göreli olarak kaydedilir.
4. **Görünüm ayarları:**
   - yazı tipi, boyut, yazı rengi
   - arka plan rengi ve saydamlığı
   - konum: üst/alt ve kenardan uzaklık
   - konuşmacı ismi rengi
   
   Panelde, TV'dekiyle birebir aynı bir canlı önizleme olur. Değişiklik bağlı ekranlara anında gider.
5. **Oyun profilleri:** Profil başına şunlar saklanır:
   - pencere adı ve bölge
   - görünüm
   - terim listesi (İngilizce → Türkçe; çevrilmeyecek isimler dahil)
   - karakter listesi
   
   Profil oluşturulabilir, seçilebilir, kopyalanabilir ve silinebilir.
6. **Konuşmacı ayırma:**
   - OCR satırı `İsim: replik` biçimindeyse isim ayrılır ve sadece replik çevrilir. İsim çevrilmez.
   - Görülen yeni isimler profilin karakter listesine kendiliğinden eklenir.
   - Karakter başına renk verilebilir; verilmezse profilin varsayılan isim rengi kullanılır.
   - Her karakter için ileride ses bilgisi tutulacak boş bir alan (`voice`) bulunur.
7. **Çeviri modeli seçimi:**
   - İyiden kötüye sıralı bir liste gösterilir. Her satırda model adı, indirme boyutu ve gereken VRAM yazar.
   - Ekran kartının VRAM'i okunur, önerilen model işaretlenir ve kartın taşıyamayacağı modeller uyarıyla gösterilir.
   - Seçilen model kurulu değilse Ollama üzerinden indirilir. Panelde ilerleme gösterilir, yarıda kalan indirme kaldığı yerden devam eder.
   - Model seçimi profile değil, genel ayarlara aittir.
8. **Durum satırı:**
   - Ollama çalışıyor mu, model hazır mı?
   - İngilizce OCR dil paketi var mı?
   - Hedef pencere bulundu mu?
   - Kaç ekran bağlı?
   - Son satırın süreleri (yakalama, OCR, çeviri)
   
   chiaki-ng'nin yolu ayarlara girilirse "Başlat" düğmesi çıkar.
9. **TV/gösterim bağlantısı:**
   - Panel, PC'nin yerel ağ adresini ve gösterim sayfasının tam adresini gösterir.
   - Gösterim sayfası bağlanınca önce görünüm ayarlarını, sonra satırları alır.
   - Satırlar `{speaker, tr, en}` biçimindedir; boş satır altyazıyı kaldırır.
   - Bağlantı koparsa sayfa kendiliğinden yeniden bağlanır.
10. **Kurulum sihirbazı (son aşama):** Inno Setup ile hazırlanır ve PyInstaller ile paketlenmiş uygulamayı kurar. Ayrıca şunları yapar:
    - Ollama'yı sessizce kurar, varsa atlar.
    - İngilizce OCR dil paketini yükler (`Add-WindowsCapability`, yönetici izniyle).
    - Uygulamanın portu için güvenlik duvarı kuralı ekler.
    - Son sayfada chiaki-ng indirme bağlantısını gösterir.
    
    Çeviri modeli sihirbazda değil, uygulamanın ilk açılışında 7. maddedeki akışla iner.
11. Kullanıcı verisi (ayarlar ve profiller) `%APPDATA%\remote-subtitle\` altında JSON dosyalarında tutulur.
12. **Sistem tepsisi:** Panel penceresi kapatılınca uygulama sistem tepsisine iner, okuma ve çeviri sürer. Tepsi simgesinden panel tekrar açılır ya da uygulamadan tamamen çıkılır. Uygulamanın aynı anda tek kopyası çalışır. Kurulum sihirbazında "Windows ile başlat" seçeneği bulunur.

## Hedef dışı (bu tur)
- Dublaj veya ses (sadece veri modeli hazır)
- Tizen paketleme ve TV'deki HDMI penceresi (TVWindow). Gösterim sayfası TV uygulamasının temeli olacak, ama paketleme ve TV'de test ayrı bir iş.
- Capture kart ya da kamera kaynağı
- Arkada kalmış veya küçültülmüş pencereyi yakalama (Windows Graphics Capture). Şimdilik pencere ekranda görünür olmalı.
- Renkle ya da ayrı satırla gösterilen konuşmacıyı tanıma (sadece `İsim:` biçimi)
- chiaki-ng'yi uygulamanın içine gömmek ya da dağıtmak (AGPL lisansı)
- Çok dilli destek (sadece İngilizce → Türkçe)

## Başarısızlık sayılacak durumlar
- Panel bir geliştirici aracı gibi görünürse (ham form, hizasız alanlar, tarayıcı sekmesi)
- Bir satırın ekranda belirmesiyle çevirinin görünmesi arasında 1 saniyeden fazla geçerse
- Ayar değişikliği için uygulamayı yeniden başlatmak gerekirse
- Kullanıcı, kurulumdan sonra komut satırı açmak ya da ayrıca bir şey kurmak zorunda kalırsa (chiaki-ng eşleştirmesi hariç)

## Kısıtlar
- Windows 11. Geliştirme makinesinde Python 3.14, RTX 5080 Laptop (16 GB) ve iki monitör var; ikinci monitörün koordinatları negatif.
- İşte PS5 yok. Test, ikinci monitörde açılan bir YouTube oynanış videosuyla yapılır. Evde sadece chiaki-ng penceresine geçilir, kod değişmez.
- Ekran ölçekleme (DPI) farklı monitörlerde koordinatları kaydırabilir. Uygulama DPI farkında olmalı (per-monitor DPI awareness).
- Çeviri modelleri Ollama'da çalışır (`localhost:11434`).

## Yaklaşımlar
| | Yaklaşım | Artı | Eksi |
|---|---|---|---|
| **A (seçildi)** | Python arka uç + HTML panel, pywebview penceresinde | Tek dil, hafif. Önizleme TV ile birebir aynı. Sonradan Electron'a taşınabilir. | Panel HTML olduğu için tasarım emeği gerekiyor (bu her seçenekte böyle) |
| B | Electron | Yaygın masaüstü kabuğu | Python yine gerekli, iki süreç ve iki dil. Kurulum yaklaşık 150 MB. |
| C | Tauri / tamamen Rust | Tek exe, hafif | Rust araç zinciri gerekiyor. OCR ve çeviri zaten yerel kod ya da GPU üzerinde, hız kazancı yok. Dublaj ekosistemi Python'da. |

Kullanıcı A'yı seçti. Görünüm üç seçenekte de aynı web motoruyla çizildiği için profesyonelliği belirleyecek olan tasarım.

## Kullanıcının kararları
- Görüntü kaynağı Remote Play (chiaki-ng). Önce bedava yol denenecek.
- Arayüz A + pywebview. Python'da kalınıyor, Rust'a geçilmiyor.
- Konuşmacı ismi farklı renkte gösterilecek. Konuşmacı bilgisi ileride dublaj için kullanılacak.
- Çeviri modeli, iyiden kötüye sıralı listeden kullanıcı tarafından seçilecek.
- Kurulum sihirbazı her şeyi arka planda kuracak.
- Tasarım taslağına gerek yok; ortaya çıkan panel değerlendirilecek.
- Panel kapatılınca uygulama sistem tepsisine iner (12. madde).

## Benim kararlarım (düzeltilebilir)
- Panel, gösterim sayfası, WebSocket ve statik dosyalar tek bir port üzerinden sunulur. Bu, kurulacak güvenlik duvarı kuralı sayısını bire indirir.
- Bölge seçimi panel içinde, anlık görüntü üzerinde yapılır; ayrı bir saydam pencere açılmaz. Daha az parça var ve her monitörde aynı çalışır.
- Konuşmacı kalıbı: satır başında en fazla 3 kelimelik, büyük harfle başlayan bir isim, ardından `:`. Tamamı büyük harfli sistem kelimeleri (`WARNING:` gibi) isim sayılmaz.
- **Birden çok OCR satırı:** Alt alta kaydırılmış satırlar birleştirilir, sonra her yeni `İsim:` görüldüğü yerden yeniden bölünür. Bir olay, blok listesi olarak gönderilir: `[{speaker, tr, en}, …]`. Gösterim sayfası blokları alt alta dizer.
- **Bölge biçimi:** Bölge, pencerenin iç alanına göre oran (0–1) olarak saklanır. Böylece pencere büyüyüp küçüldüğünde ya da tam ekrana geçtiğinde bölge de ölçeklenir ve yeniden çizmek gerekmez.
- **Model hızı:** Öneri VRAM'e göre yapılır, ayrıca hız testi yok. Gerçek süreler durum satırında gösterilir. Son satırların ortalaması 1 saniyeyi aşarsa "daha küçük model dene" uyarısı çıkar.
- **Ağ güvenliği:** Ayarları değiştiren uç noktalar sadece bu bilgisayardan (localhost) kabul edilir. TV'deki gösterim sayfası yalnızca okur.
- Varsayılan model listesi (iyiden kötüye): TranslateGemma 27B, TranslateGemma 12B, Gemma 3 12B, TranslateGemma 4B. Ollama'daki tam adlar uygulama sırasında doğrulanacak.
- Terimlerin modele nasıl verileceği (istem metnine ekleme ya da yer tutucuyla değiştirme) iki model tipiyle denenerek seçilecek. TranslateGemma sabit bir istem bekliyor olabilir.

## Uygulayıcıya kalanlar
Dosya ve modül bölümü, yazı tipi listesi, panel görsel tasarımının ayrıntıları, profilin JSON şeması, çeviri önbelleğinin diske yazılıp yazılmayacağı ve test kapsamı. Her mantık parçası (konuşmacı ayırma, satır sabitleme, bölge hesabı) çalıştırılabilir bir kontrol bırakmalı.
