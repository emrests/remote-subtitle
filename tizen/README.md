# Remote Subtitle (TR) — Samsung TV uygulaması

TV, PS5'in bağlı olduğu HDMI girişini tam ekran gösterir ve üstüne bilgisayardaki çeviri katmanını koyar.
Çeviri kutusunu bilgisayar çizer (konum ve görünüm masaüstü uygulamasındaki oyun profilinden); TV yalnız yerleştirir.
Uygulama mantığı bilgisayarda olduğu için PC tarafı güncellendiğinde TV uygulamasını yeniden kurmak gerekmez.

## Kurulum (masaüstü uygulamasından, Tizen Studio gerekmez)

Masaüstü uygulamasında **Kurulum** sekmesi → **Samsung TV uygulaması**:

1. **TV'de Geliştirici Modu**: TV'de *Uygulamalar* ekranında kumandayla **1 2 3 4 5** → *Developer mode* **On**,
   *Host PC IP* = sekmede yazan bilgisayar adresi → TV'yi kapatıp açın (güç tuşuna basılı tutun).
2. **TV'leri ara**: geliştirici modundaki TV'ler (sdb portu 26101) bulunur; model ve TV kimliği (DUID) okunur.
3. **Samsung ile giriş yap ve sertifika oluştur**: tarayıcıda kendi Samsung hesabınızla giriş yapın. Uygulama
   yazar ve dağıtıcı sertifikasını Samsung'un sertifika sunucusundan alır; bulunan TV'lerin kimlikleri sertifikaya
   eklenir. Yeni TV eklendiğinde aynı düğmeyle sertifika yenilenir (yazar sertifikası aynı kalır).
   Özel anahtarlar `%APPDATA%\remote-subtitle\tv-cert` içinde Windows DPAPI ile şifreli saklanır.
4. **Kur**: uygulama imzalanır (bilgisayarın adresi pakete yazılır), TV'ye kurulur ve açılır.

Yedek yol: Tizen Studio Certificate Manager ile oluşturulmuş bir Samsung sertifika profili
**Tizen Studio sertifikasını içe aktar** ile alınabilir (`%USERPROFILE%\SamsungCertificate\<profil>`).

## Kullanım

- TV'de *Uygulamalar* → **Remote Subtitle (TR)**. PC'de **Çeviriyi başlat** basılı olmalı.
- **Geri** tuşu uygulamadan çıkar (arka planda çalışmaz). **Kırmızı tuş**: PC adresi ve HDMI numarası ayarı.

## Teknik notlar

- Samsung sertifika arayüzü belgelenmemiştir; Tizen Studio'nun Samsung Certificate Extension'ının yaptığı istekler
  taklit edilir (`rsub/tizen_cert.py`). İmza biçimi: W3C widget dijital imzası (`rsub/tizen_sign.py`).
- İmzadaki `#prop` nesnesinin özeti her pakette aynıdır (Tizen Studio'nunkiyle birebir). lxml'in alt öğe
  kanonikleştirmesi torunlara sahte `xmlns=""` ekleyip yanlış özet veriyordu; TV paketi
  "Invalid signature … [-12]" ile reddediyordu. Bu yüzden kanonik metin elle kurulur.
- TV komutları (`rsub/tizen_device.py`, sdb):
  - Paket `/home/owner/share/tmp/sdk_tools/tmp/` klasörüne gönderilir.
  - Kurulum: `0 vd_appinstall <paket> <tam yol>`. TV'nin uygulama servisi kurar ve uygulama *Uygulamalar*
    listesinde ve aramada görünür. Yedek: `0 appinstall <paket> tmp/<dosya>` (yol `sdk_tools`'a göre; tam yol
    "realpath fail" verir). Bu yol kurar ama uygulama TV menüsünde **görünmez**.
  - Kurulum izni (`device-profile.xml` → `/home/developer`): 2024 TV yazmayı reddediyor ve gerek de yok
    (TV kimliği dağıtıcı sertifikasında); hata yok sayılır.
  - Başlatma: `0 execute <uygulama>`, kapatma: `0 kill <paket>`, kurulu uygulamalar: `0 vd_applist`.
- HDMI görüntüsü `tizen.tvwindow.show(…, "MAIN", "BEHIND")` ile gösterilir. Varsayılan z-sırası (`FRONT`) 2024 TV'de
  görüntüyü web katmanının önüne koyup çeviriyi örtüyordu.
- TV'deki gösterim sayfası (`web/display.html`, PC'den yüklenir) 2 sn'de bir `displayPing` gönderir; panel bundan
  TV'nin ekranda olup olmadığını gösterir.
- Tarayıcıda önizleme: `tizen/index.html` dosyasını açın (TV API'leri olmadığı için HDMI atlanır).
